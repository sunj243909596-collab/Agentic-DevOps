from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import TriggerEvent


class TriggerEventDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        event_id: uuid.UUID,
        event_type: str,
        source: str,
        repository_full_name: str,
        target_branch: str,
        correlation_id: uuid.UUID,
        event_timestamp: datetime,
        repository_id: uuid.UUID | None = None,
        target_sha: str | None = None,
        actor: str | None = None,
        payload_reference: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> TriggerEvent:
        event = TriggerEvent(
            event_id=event_id,
            event_type=event_type,
            source=source,
            repository_id=repository_id,
            repository_full_name=repository_full_name,
            target_branch=target_branch,
            target_sha=target_sha,
            actor=actor,
            correlation_id=correlation_id,
            payload_reference=payload_reference,
            received_at=datetime.now(UTC),
            event_timestamp=event_timestamp,
            raw_payload=raw_payload or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def get_by_id(self, event_id: uuid.UUID) -> TriggerEvent | None:
        result = await self._session.execute(
            select(TriggerEvent).where(TriggerEvent.event_id == event_id)
        )
        return result.scalar_one_or_none()
