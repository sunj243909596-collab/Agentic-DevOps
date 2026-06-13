"""S4 P5 — Suggestion + SuggestionFeedback + WebhookIdempotency DAO。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Suggestion, SuggestionFeedback, WebhookIdempotency

# ── Suggestion ──────────────────────────────────────────────────────────────


class SuggestionDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        target_type: str,
        target_id: uuid.UUID,
        suggestion_type: str,
        payload: dict[str, Any] | None = None,
        source_refs: dict[str, Any] | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> Suggestion:
        now = datetime.now(UTC)
        row = Suggestion(
            suggestion_id=uuid.uuid4(),
            target_type=target_type,
            target_id=target_id,
            suggestion_type=suggestion_type,
            payload=payload or {},
            source_refs=source_refs or {},
            status="pending",
            valid_from=valid_from or now,
            valid_to=valid_to,
            generated_at=now,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, suggestion_id: uuid.UUID) -> Suggestion | None:
        result = await self._session.execute(
            select(Suggestion).where(Suggestion.suggestion_id == suggestion_id)
        )
        return result.scalar_one_or_none()

    async def list_by_target(
        self,
        target_type: str,
        target_id: uuid.UUID,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Suggestion]:
        stmt = (
            select(Suggestion)
            .where(
                Suggestion.target_type == target_type,
                Suggestion.target_id == target_id,
            )
            .order_by(Suggestion.generated_at.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(Suggestion.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(
        self, *, suggestion_type: str | None = None, limit: int = 100,
    ) -> list[Suggestion]:
        """列出未过期、未被驳回的 suggestion。"""
        now = datetime.now(UTC)
        stmt = (
            select(Suggestion)
            .where(
                Suggestion.status.in_(("pending", "viewed")),
                Suggestion.valid_from <= now,
            )
            .order_by(Suggestion.generated_at.desc())
            .limit(limit)
        )
        # valid_to IS NULL OR valid_to > now
        from sqlalchemy import or_
        stmt = stmt.where(or_(Suggestion.valid_to.is_(None), Suggestion.valid_to > now))
        if suggestion_type is not None:
            stmt = stmt.where(Suggestion.suggestion_type == suggestion_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, suggestion_id: uuid.UUID, status: str,
    ) -> bool:
        from sqlalchemy import update as sa_update
        result = await self._session.execute(
            sa_update(Suggestion)
            .where(Suggestion.suggestion_id == suggestion_id)
            .values(status=status)
        )
        return (result.rowcount or 0) > 0


# ── SuggestionFeedback ──────────────────────────────────────────────────────


class SuggestionFeedbackDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        suggestion_id: uuid.UUID,
        actor: str,
        feedback_type: str,
        comment: str | None = None,
    ) -> SuggestionFeedback:
        row = SuggestionFeedback(
            feedback_id=uuid.uuid4(),
            suggestion_id=suggestion_id,
            actor=actor,
            feedback_type=feedback_type,
            comment=comment,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_suggestion(
        self, suggestion_id: uuid.UUID,
    ) -> list[SuggestionFeedback]:
        result = await self._session.execute(
            select(SuggestionFeedback)
            .where(SuggestionFeedback.suggestion_id == suggestion_id)
            .order_by(SuggestionFeedback.created_at.asc())
        )
        return list(result.scalars().all())


# ── WebhookIdempotency ──────────────────────────────────────────────────────


class WebhookIdempotencyDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self, *, idempotency_key: str, source: str, event_type: str,
    ) -> WebhookIdempotency:
        """首次插入；若已存在（重复 webhook）则返回 None，调用方应忽略。

        使用 SELECT FOR UPDATE 模式由调用方在事务内保证；此处直接 INSERT。
        """
        try:
            row = WebhookIdempotency(
                idempotency_key=idempotency_key,
                source=source,
                event_type=event_type,
                received_at=datetime.now(UTC),
                status="received",
            )
            self._session.add(row)
            await self._session.flush()
            return row
        except Exception:
            await self._session.rollback()
            return None  # type: ignore[return-value]

    async def get(self, idempotency_key: str) -> WebhookIdempotency | None:
        result = await self._session.execute(
            select(WebhookIdempotency).where(
                WebhookIdempotency.idempotency_key == idempotency_key
            )
        )
        return result.scalar_one_or_none()

    async def mark_processed(
        self, idempotency_key: str, *, error: str | None = None,
    ) -> bool:
        from sqlalchemy import update as sa_update
        status = "failed" if error else "processed"
        result = await self._session.execute(
            sa_update(WebhookIdempotency)
            .where(WebhookIdempotency.idempotency_key == idempotency_key)
            .values(
                status=status,
                processed_at=datetime.now(UTC),
                error_message=error,
            )
        )
        return (result.rowcount or 0) > 0
