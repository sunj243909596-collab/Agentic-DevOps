from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import AuditEvent


class AuditEventDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        actor: str,
        workflow_id: uuid.UUID | None,
        event_type: str,
        event_timestamp: datetime,
        tool: str | None = None,
        input_ref: str | None = None,
        output_ref: str | None = None,
        model_version: str | None = None,
        prompt_version: str | None = None,
        policy_version: str | None = None,
        policy_decision: str | None = None,
        approval_identity: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=uuid.uuid4(),
            actor=actor,
            workflow_id=workflow_id,
            event_type=event_type,
            tool=tool,
            input_ref=input_ref,
            output_ref=output_ref,
            model_version=model_version,
            prompt_version=prompt_version,
            policy_version=policy_version,
            policy_decision=policy_decision,
            approval_identity=approval_identity,
            event_metadata=metadata or {},
            event_timestamp=event_timestamp,
            inserted_at=datetime.now(UTC),
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_by_workflow(
        self,
        workflow_id: uuid.UUID,
        limit: int = 100,
    ) -> list[AuditEvent]:
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.workflow_id == workflow_id)
            .order_by(AuditEvent.event_timestamp.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
