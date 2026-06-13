from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.audit_event import AuditEventDAO
from devmanager_db.daos.change_unit import ChangeUnitDAO
from devmanager_db.daos.finding import FindingDAO
from devmanager_db.daos.report import ReportDAO
from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.daos.score import ScoreDAO
from devmanager_db.models import Report
from devmanager_reporting.renderer import render_markdown

log = logging.getLogger(__name__)

_REPORTS_ROOT = Path(os.getenv("REPORTS_DIR", "/tmp/devmanager/reports"))


class ReportError(Exception):
    pass


class AlreadyReportedError(ReportError):
    pass


async def generate_report(run_id: uuid.UUID, db: AsyncSession) -> Report:
    """
    Render a Markdown report for a completed analysis run and persist it.

    Raises:
        ReportError:        run or required data not found.
        AlreadyReportedError: report already exists for this run.
    """
    run_dao = AnalysisRunDAO(db)
    repo_dao = RepositoryDAO(db)
    score_dao = ScoreDAO(db)
    finding_dao = FindingDAO(db)
    cu_dao = ChangeUnitDAO(db)
    report_dao = ReportDAO(db)
    audit_dao = AuditEventDAO(db)

    run = await run_dao.get_by_id(run_id)
    if run is None:
        raise ReportError(f"AnalysisRun {run_id} not found")

    existing = await report_dao.get_by_run(run_id)
    if existing is not None:
        raise AlreadyReportedError(
            f"Run {run_id} already has a report (report_id={existing.report_id})"
        )

    repo = await repo_dao.get_by_id(run.repository_id)
    repository_full_name = repo.full_name if repo else str(run.repository_id)

    score = await score_dao.get_by_run(run_id)
    findings = await finding_dao.list_by_run(run_id)
    change_units = await cu_dao.list_by_run(run_id)

    markdown = render_markdown(
        run=run,
        repository_full_name=repository_full_name,
        score=score,
        findings=findings,
        change_units=change_units,
    )

    # Write markdown to file
    _REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = _REPORTS_ROOT / f"{run_id}.md"
    report_path.write_text(markdown, encoding="utf-8")
    content_reference = f"file://{report_path}"

    generated_at = datetime.now(timezone.utc)
    report = await report_dao.create(
        run_id=run_id,
        report_type="daily_markdown",
        status="generated",
        content_reference=content_reference,
        generated_at=generated_at,
    )

    # Emit audit event (best-effort)
    try:
        await audit_dao.append(
            actor="system",
            workflow_id=run_id,
            event_type="run.report_generated",
            event_timestamp=generated_at,
            output_ref=content_reference,
            metadata={
                "report_id": str(report.report_id),
                "findings_count": len(findings),
                "score": float(score.final_score) if score and score.final_score else None,
                "grade": score.grade if score else None,
            },
        )
    except Exception as exc:
        log.warning("Failed to emit audit event for report %s: %s", run_id, exc)

    await db.commit()
    return report
