from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.audit_event import AuditEventDAO
from devmanager_db.daos.change_unit import ChangeUnitDAO
from devmanager_db.daos.finding import FindingDAO
from devmanager_db.models import ChangeUnit, Finding
from devmanager_db.schema_validator import validate
from devmanager_llm import LLMProvider
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_agents.agent_reviewer import AgentReviewer
from devmanager_agents.filters import is_worth_reviewing
from devmanager_agents.skills import default_registry

log = logging.getLogger(__name__)


class ReviewError(Exception):
    pass


def _dedupe_key(
    repository: str,
    file: str,
    category: str,
    start_line: int,
    observation: str,
) -> str:
    raw = f"{repository}::{file}::{category}::{start_line}::{observation[:40]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _enrich_finding(f: dict, unit: ChangeUnit) -> dict:
    """Fill required fields from change-unit context when the agent omits them."""
    f.setdefault("repository", unit.repository_full_name)
    if not f.get("file"):
        f["file"] = unit.file_path
    if not f.get("evidence_refs"):
        s = f.get("start_line", 1)
        e = f.get("end_line", s)
        f["evidence_refs"] = [f"diff:{f['file']}:{s}-{e}"]
    try:
        f["start_line"] = max(1, int(f.get("start_line", 1)))
        f["end_line"] = max(f["start_line"], int(f.get("end_line", f["start_line"])))
    except (TypeError, ValueError):
        f["start_line"] = 1
        f["end_line"] = 1
    try:
        f["confidence"] = max(0.0, min(1.0, float(f.get("confidence", 0.7))))
    except (TypeError, ValueError):
        f["confidence"] = 0.7
    for field in ("observation", "impact", "recommendation", "verification"):
        if not f.get(field):
            f[field] = f"(see diff: {f['file']})"
    return f


async def review_run(
    run_id: uuid.UUID,
    db: AsyncSession,
    provider: LLMProvider,
    concurrency: int = 3,
    repo_dir: Path | None = None,
) -> list[Finding]:
    run_dao = AnalysisRunDAO(db)
    cu_dao = ChangeUnitDAO(db)
    finding_dao = FindingDAO(db)
    audit_dao = AuditEventDAO(db)

    run = await run_dao.get_by_id(run_id)
    if run is None:
        raise ReviewError(f"AnalysisRun {run_id} not found")

    units = await cu_dao.list_by_run(run_id)
    if repo_dir is not None:
        reviewable = [
            u
            for u in units
            if is_worth_reviewing(
                file_path=u.file_path,
                repo_dir=repo_dir,
                is_binary=u.is_binary,
                is_generated=u.is_generated,
                is_vendor=u.is_vendor,
                added_lines=u.added_lines,
                deleted_lines=u.deleted_lines,
                language=u.language,
            )
        ]
        skipped = len(units) - len(reviewable)
        if skipped:
            log.info("review_run %s: skipped %d/%d units (pre-filter)", run_id, skipped, len(units))
    else:
        reviewable = [u for u in units if not (u.is_binary or u.is_generated or u.is_vendor)]

    await run_dao.update_status(run_id, "agent_review_started")
    try:
        await audit_dao.append(
            actor="system",
            workflow_id=run_id,
            event_type="agent.review_started",
            event_timestamp=datetime.now(UTC),
            metadata={"reviewable_units": len(reviewable), "mode": "agent_loop"},
        )
    except Exception as exc:
        log.warning("Failed to emit audit event review_started %s: %s", run_id, exc)
    await db.commit()

    if not reviewable:
        await run_dao.update_status(run_id, "agent_review_completed")
        await db.commit()
        return []

    registry = default_registry()
    reviewer = AgentReviewer(provider, registry, max_iter=10)
    sem = asyncio.Semaphore(concurrency)
    effective_repo = repo_dir or Path("/tmp")

    async def _run_agent(cu: ChangeUnit) -> list[dict]:
        async with sem:
            try:
                findings = await reviewer.review_all(
                    [cu],
                    repo_dir=effective_repo,
                    audit_dao=audit_dao,
                    workflow_id=run_id,
                    db=db,
                )
                try:
                    await audit_dao.append(
                        actor="agent",
                        workflow_id=run_id,
                        event_type="agent.review_completed",
                        event_timestamp=datetime.now(UTC),
                        metadata={"file": cu.file_path, "findings": len(findings)},
                    )
                except Exception as exc:
                    log.warning("audit review_completed failed for %s: %s", cu.file_path, exc)
                return [_enrich_finding(f, cu) for f in findings]
            except Exception as exc:
                log.warning("agent review failed for %s: %s", cu.file_path, exc)
                return []

    results = await asyncio.gather(*[_run_agent(cu) for cu in reviewable])
    raw_findings: list[dict] = [f for batch in results for f in batch]

    today = datetime.now(UTC).strftime("%Y%m%d")
    for idx, f in enumerate(raw_findings, start=1):
        f["finding_id"] = f"F-{today}-{idx:03d}"
        f["run_id"] = str(run_id)
        f["commit_sha"] = run.target_sha[:40] if run.target_sha else "0" * 7
        f["status"] = "open"
        f.setdefault("related_knowledge_refs", [])
        f["dedupe_key"] = _dedupe_key(
            f.get("repository", ""),
            f.get("file", ""),
            f.get("category", ""),
            f.get("start_line", 0),
            f.get("observation", ""),
        )

    db_findings: list[Finding] = []
    for f in raw_findings:
        errors = validate(f, "reviewer-finding")
        if errors:
            log.warning("Invalid finding skipped: %s — %s", f.get("finding_id"), errors)
            continue
        try:
            db_finding = await finding_dao.create(run_id=run_id, data=f)
            db_findings.append(db_finding)
        except Exception as exc:
            log.warning("Failed to persist finding %s: %s", f.get("finding_id"), exc)

    await run_dao.update_status(run_id, "agent_review_completed")
    try:
        await audit_dao.append(
            actor="system",
            workflow_id=run_id,
            event_type="agent.review_completed",
            event_timestamp=datetime.now(UTC),
            metadata={"findings_persisted": len(db_findings)},
        )
    except Exception as exc:
        log.warning("Failed to emit audit event review_completed %s: %s", run_id, exc)
    await db.commit()

    return db_findings
