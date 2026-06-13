from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.baseline import BaselineDAO
from devmanager_db.daos.change_unit import ChangeUnitDAO
from devmanager_db.daos.finding import FindingDAO
from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.daos.score import ScoreDAO
from devmanager_db.daos.trigger_event import TriggerEventDAO
from devmanager_db.models import (
    AnalysisRun,
    AuditEvent,
    ChangeUnit,
    Finding,
    FindingStatusHistory,
    Report,
    ReviewTask,
    Score,
)
from devmanager_git.service import IngestionError
from devmanager_git.service import ingest as git_ingest
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from api_gateway.queue import get_arq_pool
from api_gateway.schemas.models import (
    AnalysisRunResponse,
    ChangeUnitResponse,
    CreateAnalysisRunIn,
    FindingResponse,
    ReportResponse,
    ScoreResponse,
)

router = APIRouter(prefix="/v1/analysis-runs", tags=["analysis-runs"])

_NULL_SHA = "0" * 40
_POLICY_VERSION = os.getenv("POLICY_VERSION", "v1")
_SCORING_VERSION = os.getenv("SCORING_VERSION", "v1")


@router.get("", response_model=dict)
async def list_analysis_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    runs = await AnalysisRunDAO(db).list_recent(limit=limit, offset=offset)
    return {"items": [AnalysisRunResponse.model_validate(r) for r in runs]}


@router.post("", status_code=202, response_model=AnalysisRunResponse)
async def create_analysis_run(
    body: CreateAnalysisRunIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
    pool=Depends(get_arq_pool),
) -> AnalysisRunResponse:
    repo_dao = RepositoryDAO(db)
    baseline_dao = BaselineDAO(db)
    run_dao = AnalysisRunDAO(db)

    repo = await repo_dao.get_by_full_name(body.repository)
    if repo is None:
        repo = await repo_dao.create(
            provider=body.provider or "other",
            full_name=body.repository,
            clone_url=body.clone_url,
        )
    elif body.provider and body.provider != repo.provider:
        # Repo already exists with a different provider — overwrite provider tag
        await repo_dao.update(repo.repository_id, provider=body.provider)
        if body.clone_url and not repo.clone_url:
            await repo_dao.update_clone_url(repo.repository_id, body.clone_url)
    else:
        if body.clone_url and not repo.clone_url:
            await repo_dao.update_clone_url(repo.repository_id, body.clone_url)
    if body.access_token is not None:
        await repo_dao.update_access_token(repo.repository_id, body.access_token)

    baseline = await baseline_dao.get(repo.repository_id, body.target_branch)
    baseline_sha = baseline.last_successful_sha if baseline else _NULL_SHA
    target_sha = body.target_sha or _NULL_SHA

    run = await run_dao.create(
        repository_id=repo.repository_id,
        repository_full_name=repo.full_name,
        trigger_type="manual",
        target_branch=body.target_branch,
        baseline_sha=baseline_sha,
        target_sha=target_sha,
        status="trigger_received",
        policy_version=_POLICY_VERSION,
        scoring_version=_SCORING_VERSION,
    )
    await db.commit()
    if pool is not None:
        try:
            await pool.enqueue_job("full_pipeline", str(run.run_id))
        except Exception as exc:
            # If we can't even enqueue, roll back the run so caller can retry cleanly
            await db.rollback()
            raise HTTPException(status_code=503, detail=f"Task queue unavailable: {exc}")
    try:
        return AnalysisRunResponse.model_validate(run)
    except Exception:
        # Response serialization failed (e.g. Pydantic mismatch) — roll back to avoid orphan
        await db.rollback()
        raise


@router.get("/{run_id}", response_model=AnalysisRunResponse)
async def get_analysis_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> AnalysisRunResponse:
    run = await AnalysisRunDAO(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")
    return AnalysisRunResponse.model_validate(run)


@router.get("/{run_id}/change-units")
async def list_change_units(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    units = await ChangeUnitDAO(db).list_by_run(run_id)
    return {"items": [ChangeUnitResponse.model_validate(u) for u in units]}


@router.get("/{run_id}/findings")
async def list_findings(
    run_id: uuid.UUID,
    severity: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    findings = await FindingDAO(db).list_by_run(run_id, severity=severity, status=status)
    return {"items": [FindingResponse.model_validate(f) for f in findings]}


@router.get("/{run_id}/score", response_model=ScoreResponse)
async def get_score(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> ScoreResponse:
    score = await ScoreDAO(db).get_by_run(run_id)
    if score is None:
        raise HTTPException(status_code=404, detail=f"Score not found for run {run_id}")
    return ScoreResponse.model_validate(score)


@router.post("/{run_id}/ingest", status_code=200)
async def trigger_ingest(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    try:
        units = await git_ingest(run_id, db)
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "run_id": str(run_id),
        "change_units_count": len(units),
        "items": [ChangeUnitResponse.model_validate(u) for u in units],
    }


# Statuses that are allowed to be retried. A retry creates a *new* run
# (new run_id) that reuses the original's target_branch/baseline/target_sha;
# trigger_id on the new run points to the original so the lineage is
# queryable. Old finding/score/report rows are NOT cleared — they remain
# attached to the original run_id for the audit trail.
RETRYABLE_STATUSES = frozenset({"failed", "partial_analysis", "rejected"})


@router.post("/{run_id}/retry", status_code=202, response_model=AnalysisRunResponse)
async def retry_analysis_run(
    run_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
    pool=Depends(get_arq_pool),
) -> AnalysisRunResponse:
    """Re-pull the code and re-run the full analysis pipeline for a failed run.

    Creates a NEW AnalysisRun with a fresh run_id, copying the original's
    repository / target_branch / baseline_sha / target_sha. Because
    `analysis_runs.trigger_id` is FK-bound to `trigger_events.event_id`
    (not to runs.run_id), we first create a `TriggerEvent` of
    `event_type='retry'` and point the new run's `trigger_id` at it.
    The original run's id is stashed in the event's `payload_reference`
    and `raw_payload.retry_of_run_id` so the lineage is still queryable.

    Old finding / score / report rows are preserved on the original run —
    they remain valid historical records of what happened last time.
    Only allowed when the original run is in a terminal failure status.
    """
    run_dao = AnalysisRunDAO(db)
    original = await run_dao.get_by_id(run_id)
    if original is None:
        raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")
    if original.status not in RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot retry run in status {original.status!r}; "
                f"only {sorted(RETRYABLE_STATUSES)} are retryable"
            ),
        )

    # A retry must produce a TriggerEvent first because analysis_runs.trigger_id
    # is FK-bound to trigger_events.event_id (not to runs.run_id). The event row
    # is what the data model considers a "trigger" — the human clicking the
    # retry button is the source event. We stash the original run_id in
    # payload_reference so the lineage is still queryable end-to-end.
    trigger_dao = TriggerEventDAO(db)
    retry_event = await trigger_dao.create(
        event_id=uuid.uuid4(),
        event_type="retry",
        source="manual",
        repository_id=original.repository_id,
        repository_full_name=original.repository_full_name,
        target_branch=original.target_branch,
        target_sha=original.target_sha,
        actor=None,  # TODO: thread auth user once require_auth returns a user id
        correlation_id=uuid.uuid4(),
        event_timestamp=datetime.now(UTC),
        payload_reference=f"retry_of:{original.run_id}",
        raw_payload={"retry_of_run_id": str(original.run_id)},
    )

    new_run = await run_dao.create(
        repository_id=original.repository_id,
        repository_full_name=original.repository_full_name,
        trigger_type="manual",
        trigger_id=retry_event.event_id,
        target_branch=original.target_branch,
        baseline_sha=original.baseline_sha,
        target_sha=original.target_sha,
        status="trigger_received",
        policy_version=_POLICY_VERSION,
        scoring_version=_SCORING_VERSION,
    )
    await db.commit()

    if pool is not None:
        try:
            await pool.enqueue_job("full_pipeline", str(new_run.run_id))
        except Exception as exc:
            # If we can't enqueue, roll back so the caller can retry cleanly.
            # The new run row never existed as far as the queue is concerned.
            await db.rollback()
            raise HTTPException(status_code=503, detail=f"Task queue unavailable: {exc}")

    return AnalysisRunResponse.model_validate(new_run)


@router.get("/{run_id}/report", response_model=ReportResponse)
async def get_report(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> ReportResponse:
    result = await db.execute(select(Report).where(Report.run_id == run_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report not found for run {run_id}")
    return ReportResponse.model_validate(report)


@router.delete("/{run_id}", status_code=204)
async def delete_analysis_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> Response:
    """Delete a run and all related rows (audit trail preserved with workflow_id set NULL).

    Cascade order:
      finding_status_history → review_tasks → findings → scores → reports
      → change_units → audit_events → analysis_run
    Audit events are NOT deleted — their workflow_id is set NULL so the
    audit trail survives.
    """
    run = await AnalysisRunDAO(db).get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")

    # findings → finding_status_history cascade first
    findings_result = await db.execute(select(Finding.finding_pk).where(Finding.run_id == run_id))
    finding_pks = [row[0] for row in findings_result.all()]
    if finding_pks:
        await db.execute(
            delete(FindingStatusHistory).where(FindingStatusHistory.finding_pk.in_(finding_pks))
        )
    await db.execute(delete(Finding).where(Finding.run_id == run_id))
    await db.execute(delete(ReviewTask).where(ReviewTask.run_id == run_id))
    await db.execute(delete(Score).where(Score.run_id == run_id))
    await db.execute(delete(Report).where(Report.run_id == run_id))
    await db.execute(delete(ChangeUnit).where(ChangeUnit.run_id == run_id))
    # audit events: keep rows, null out workflow_id
    await db.execute(
        AuditEvent.__table__.update()
        .where(AuditEvent.workflow_id == run_id)
        .values(workflow_id=None)
    )
    await db.execute(delete(AnalysisRun).where(AnalysisRun.run_id == run_id))
    await db.commit()
    return Response(status_code=204)
