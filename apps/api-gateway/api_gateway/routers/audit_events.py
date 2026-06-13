from __future__ import annotations

import uuid

from devmanager_db.models import AuditEvent
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from api_gateway.schemas.models import AuditEventResponse

router = APIRouter(prefix="/v1/audit-events", tags=["audit-events"])


@router.get("")
async def list_audit_events(
    workflow_id: uuid.UUID | None = None,
    event_type: str | None = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    stmt = select(AuditEvent).order_by(AuditEvent.event_timestamp.desc()).limit(limit)
    if workflow_id is not None:
        stmt = stmt.where(AuditEvent.workflow_id == workflow_id)
    if event_type is not None:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    result = await db.execute(stmt)
    events = result.scalars().all()
    return {"items": [AuditEventResponse.model_validate(e) for e in events]}
