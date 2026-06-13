from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.audit_event import AuditEventDAO
from devmanager_db.daos.change_unit import ChangeUnitDAO
from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.daos.setting import SettingDAO
from devmanager_db.models import AnalysisRun
from devmanager_git.codeowners import CodeownersParser
from devmanager_git.differ import parse_diff
from devmanager_git.fetcher import (
    GitError,
    _NULL_SHA,
    clone_or_fetch,
    detect_history_rewrite,
    get_diff_name_status,
    get_diff_numstat,
    resolve_merge_base,
    resolve_sha,
)
from devmanager_git.hunks import extract_all_hunks

# Defaults used when settings table is empty (e.g. before migration 004)
_DEFAULT_WORKSPACE = Path(os.getenv("GIT_WORKSPACE", "/tmp/devmanager/repos"))
_DEFAULT_HUNKS = Path(os.getenv("GIT_HUNKS_DIR", "/tmp/devmanager/hunks"))


async def _get_paths(db: AsyncSession) -> tuple[Path, Path]:
    """Read current workspace / hunks paths from settings, falling back to defaults."""
    dao = SettingDAO(db)
    ws = await dao.get_value("git_workspace") or str(_DEFAULT_WORKSPACE)
    hk = await dao.get_value("git_hunks_dir") or str(_DEFAULT_HUNKS)
    return Path(ws), Path(hk)


def _repo_dir(workspace_root: Path, repository_id: uuid.UUID) -> Path:
    return workspace_root / str(repository_id)


def _hunks_dir(hunks_root: Path, run_id: uuid.UUID) -> Path:
    return hunks_root / str(run_id)


class IngestionError(Exception):
    pass


async def ingest(run_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    workspace_root, hunks_root = await _get_paths(db)
    run_dao = AnalysisRunDAO(db)
    repo_dao = RepositoryDAO(db)
    cu_dao = ChangeUnitDAO(db)
    audit_dao = AuditEventDAO(db)

    run = await run_dao.get_by_id(run_id)
    if run is None:
        raise IngestionError(f"AnalysisRun {run_id} not found")

    repo = await repo_dao.get_by_id(run.repository_id)
    if repo is None:
        raise IngestionError(f"Repository {run.repository_id} not found")

    if not repo.clone_url:
        raise IngestionError(
            f"Repository {repo.full_name} has no clone_url — cannot fetch"
        )

    # ── Phase 1: fetch ────────────────────────────────────────────────────────
    await run_dao.update_status(run_id, "git_fetching")
    try:
        await audit_dao.append(
            actor="system",
            workflow_id=run_id,
            event_type="run.ingest_started",
            event_timestamp=datetime.now(timezone.utc),
            metadata={"repository": repo.full_name, "target_sha": run.target_sha},
        )
    except Exception:
        pass
    await db.commit()

    repo_dir = _repo_dir(workspace_root, repo.repository_id)
    try:
        await clone_or_fetch(repo.clone_url, repo_dir, access_token=getattr(repo, "access_token", None))
    except GitError as exc:
        await run_dao.update_status(run_id, "failed", failure_reason=str(exc))
        await db.commit()
        raise IngestionError(str(exc)) from exc

    # ── Phase 2: baseline resolution ─────────────────────────────────────────
    baseline_sha = run.baseline_sha
    target_sha = run.target_sha

    # If target_sha is NULL_SHA (i.e. the run was triggered without a specific SHA),
    # fall back to the default branch's HEAD. Without this, the diff step below
    # would error with "fatal: bad object 0000...".
    if target_sha == _NULL_SHA:
        target_sha = await resolve_sha(repo_dir, repo.default_branch or "main")

    merge_base = await resolve_merge_base(repo_dir, baseline_sha, target_sha)
    history_rewrite = await detect_history_rewrite(repo_dir, baseline_sha, target_sha)

    # ── Phase 3: diff extraction ──────────────────────────────────────────────
    try:
        numstat = await get_diff_numstat(repo_dir, merge_base, target_sha)
        name_status = await get_diff_name_status(repo_dir, merge_base, target_sha)
    except GitError as exc:
        await run_dao.update_status(run_id, "failed", failure_reason=str(exc))
        await db.commit()
        raise IngestionError(str(exc)) from exc

    # ── Phase 4: parse → ChangeUnit dicts ────────────────────────────────────
    units = parse_diff(
        numstat=numstat,
        name_status=name_status,
        run_id=run_id,
        repository_full_name=repo.full_name,
        baseline_sha=baseline_sha,
        target_sha=target_sha,
    )

    # ── Phase 5: CODEOWNERS owner assignment ─────────────────────────────────
    codeowners = CodeownersParser.from_bare_repo(repo_dir)
    if codeowners is not None:
        for unit in units:
            owner = codeowners.find_owner(unit["file_path"])
            if owner:
                unit["owner"] = owner

    # ── Phase 6: persist ChangeUnits ─────────────────────────────────────────
    db_units: list = []
    if units:
        db_units = await cu_dao.bulk_create(units)

    # ── Phase 7: hunk extraction (async, non-blocking on failure) ────────────
    if units:
        try:
            hunks_map = await extract_all_hunks(
                repo_dir=repo_dir,
                from_ref=merge_base,
                to_ref=target_sha,
                units=units,
                hunks_dir=_hunks_dir(hunks_root, run_id),
            )
            if hunks_map:
                updates = {
                    cu_id: {"hunks_ref": ref} for cu_id, ref in hunks_map.items()
                }
                await cu_dao.bulk_update_hunks_and_owners(updates)
        except Exception:
            pass  # hunk extraction is best-effort; don't fail ingestion

    # ── Phase 8: finalise run ─────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    await db.execute(
        update(AnalysisRun)
        .where(AnalysisRun.run_id == run_id)
        .values(
            merge_base_sha=merge_base,
            history_rewrite_detected=history_rewrite,
            status="git_ingested",
        )
    )
    try:
        await audit_dao.append(
            actor="system",
            workflow_id=run_id,
            event_type="run.ingest_completed",
            event_timestamp=now,
            metadata={
                "files_changed": len(units),
                "merge_base_sha": merge_base,
                "history_rewrite": history_rewrite,
            },
        )
    except Exception:
        pass
    await db.commit()

    return units
