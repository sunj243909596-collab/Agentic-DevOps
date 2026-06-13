from __future__ import annotations

import os

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.baseline import BaselineDAO
from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.daos.trigger_event import TriggerEventDAO
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from api_gateway.schemas.models import TriggerEventIn, TriggerEventOut

router = APIRouter(prefix="/v1/trigger-events", tags=["trigger-events"])

_NULL_SHA = "0" * 40
_POLICY_VERSION = os.getenv("POLICY_VERSION", "v1")
_SCORING_VERSION = os.getenv("SCORING_VERSION", "v1")


@router.post("", status_code=202, response_model=TriggerEventOut)
async def create_trigger_event(
    body: TriggerEventIn,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> TriggerEventOut:
    repo_dao = RepositoryDAO(db)
    trigger_dao = TriggerEventDAO(db)
    baseline_dao = BaselineDAO(db)
    run_dao = AnalysisRunDAO(db)

    repo = await repo_dao.get_by_full_name(body.repository)
    if repo is None:
        repo = await repo_dao.create(provider="other", full_name=body.repository)

    existing = await trigger_dao.get_by_id(body.event_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Trigger event already exists")

    trigger = await trigger_dao.create(
        event_id=body.event_id,
        event_type=body.event_type,
        source=body.source,
        repository_id=repo.repository_id,
        repository_full_name=body.repository,
        target_branch=body.target_branch,
        target_sha=body.target_sha,
        actor=body.actor,
        correlation_id=body.correlation_id,
        event_timestamp=body.event_timestamp,
        payload_reference=body.payload_reference,
    )

    baseline = await baseline_dao.get(repo.repository_id, body.target_branch)
    baseline_sha = baseline.last_successful_sha if baseline else _NULL_SHA

    target_sha = body.target_sha or _NULL_SHA
    run = await run_dao.create(
        repository_id=repo.repository_id,
        trigger_id=trigger.event_id,
        trigger_type=body.event_type,
        target_branch=body.target_branch,
        baseline_sha=baseline_sha,
        target_sha=target_sha,
        status="trigger_received",
        policy_version=_POLICY_VERSION,
        scoring_version=_SCORING_VERSION,
    )

    await db.commit()
    return TriggerEventOut(run_id=run.run_id)
