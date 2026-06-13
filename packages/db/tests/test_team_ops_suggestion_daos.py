"""S4 P5 — Suggestion / SuggestionFeedback / WebhookIdempotency DAO 单测。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from devmanager_db.daos.team_ops.suggestion import (
    SuggestionDAO,
    SuggestionFeedbackDAO,
    WebhookIdempotencyDAO,
)
from devmanager_db.models import (
    Suggestion,
    SuggestionFeedback,
    WebhookIdempotency,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    yield
    await session.rollback()
    await session.execute(delete(SuggestionFeedback))
    await session.execute(delete(Suggestion))
    await session.execute(delete(WebhookIdempotency))
    await session.commit()


# ── SuggestionDAO ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suggestion_create_and_get(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = SuggestionDAO(session)
    target_id = uuid.uuid4()
    row = await dao.create(
        target_type="person",
        target_id=target_id,
        suggestion_type="sprint_planning",
        payload={"facts": ["本周 12h 剩余"], "trends": [], "notes": []},
        source_refs={"workload_snapshot": ["..."]},
    )
    fetched = await dao.get(row.suggestion_id)
    assert fetched is not None
    assert fetched.target_id == target_id
    assert fetched.status == "pending"
    assert fetched.payload["facts"] == ["本周 12h 剩余"]


@pytest.mark.asyncio
async def test_suggestion_update_status(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = SuggestionDAO(session)
    row = await dao.create(
        target_type="team",
        target_id=uuid.uuid4(),
        suggestion_type="priority",
        payload={"facts": [], "trends": [], "notes": []},
    )
    assert await dao.update_status(row.suggestion_id, "viewed") is True
    fetched = await dao.get(row.suggestion_id)
    assert fetched.status == "viewed"


@pytest.mark.asyncio
async def test_suggestion_list_active_excludes_dismissed_and_expired(
    session: AsyncSession,
    cleanup: None,
) -> None:
    from datetime import UTC, datetime, timedelta

    dao = SuggestionDAO(session)
    # pending, 未来生效 → 不在 active
    future_row = await dao.create(
        target_type="person",
        target_id=uuid.uuid4(),
        suggestion_type="growth",
        payload={"facts": [], "trends": [], "notes": []},
        valid_from=datetime.now(UTC) + timedelta(days=10),
    )
    # pending, 当前生效 → 在 active
    active_row = await dao.create(
        target_type="person",
        target_id=uuid.uuid4(),
        suggestion_type="growth",
        payload={"facts": [], "trends": [], "notes": []},
    )
    # dismissed → 不在 active
    dismissed_row = await dao.create(
        target_type="person",
        target_id=uuid.uuid4(),
        suggestion_type="growth",
        payload={"facts": [], "trends": [], "notes": []},
    )
    await dao.update_status(dismissed_row.suggestion_id, "dismissed")

    active = await dao.list_active()
    active_ids = {r.suggestion_id for r in active}
    assert active_row.suggestion_id in active_ids
    assert future_row.suggestion_id not in active_ids
    assert dismissed_row.suggestion_id not in active_ids


@pytest.mark.asyncio
async def test_suggestion_list_by_target(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = SuggestionDAO(session)
    target_id = uuid.uuid4()
    await dao.create(
        target_type="person",
        target_id=target_id,
        suggestion_type="task_assignment",
        payload={"facts": [], "trends": [], "notes": []},
    )
    await dao.create(
        target_type="person",
        target_id=target_id,
        suggestion_type="growth",
        payload={"facts": [], "trends": [], "notes": []},
    )
    # 其他 target
    await dao.create(
        target_type="person",
        target_id=uuid.uuid4(),
        suggestion_type="growth",
        payload={"facts": [], "trends": [], "notes": []},
    )

    items = await dao.list_by_target("person", target_id)
    assert len(items) == 2
    types = {i.suggestion_type for i in items}
    assert types == {"task_assignment", "growth"}


# ── SuggestionFeedbackDAO ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feedback_record_and_list(
    session: AsyncSession,
    cleanup: None,
) -> None:
    s_dao = SuggestionDAO(session)
    f_dao = SuggestionFeedbackDAO(session)
    s = await s_dao.create(
        target_type="person",
        target_id=uuid.uuid4(),
        suggestion_type="priority",
        payload={"facts": [], "trends": [], "notes": []},
    )
    await f_dao.record(
        suggestion_id=s.suggestion_id,
        actor="alice",
        feedback_type="viewed",
    )
    await f_dao.record(
        suggestion_id=s.suggestion_id,
        actor="alice",
        feedback_type="accepted",
        comment="useful",
    )
    feedbacks = await f_dao.list_by_suggestion(s.suggestion_id)
    assert len(feedbacks) == 2
    assert feedbacks[0].feedback_type == "viewed"
    assert feedbacks[1].comment == "useful"


# ── WebhookIdempotencyDAO ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_idempotency_reserve_then_duplicate(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = WebhookIdempotencyDAO(session)
    first = await dao.reserve(
        idempotency_key="gitlab:abc-123",
        source="gitlab",
        event_type="Merge Request Hook",
    )
    assert first is not None
    assert first.status == "received"

    # 第二次 reserve 重复 key → 应返回 None
    second = await dao.reserve(
        idempotency_key="gitlab:abc-123",
        source="gitlab",
        event_type="Merge Request Hook",
    )
    assert second is None


@pytest.mark.asyncio
async def test_webhook_idempotency_mark_processed(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = WebhookIdempotencyDAO(session)
    await dao.reserve(
        idempotency_key="pm:evt-1",
        source="pm",
        event_type="issue.updated",
    )
    ok = await dao.mark_processed("pm:evt-1")
    assert ok is True
    row = await dao.get("pm:evt-1")
    assert row.status == "processed"
    assert row.processed_at is not None


@pytest.mark.asyncio
async def test_webhook_idempotency_mark_failed(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = WebhookIdempotencyDAO(session)
    await dao.reserve(
        idempotency_key="pm:evt-2",
        source="pm",
        event_type="issue.deleted",
    )
    ok = await dao.mark_processed("pm:evt-2", error="validation failed")
    assert ok is True
    row = await dao.get("pm:evt-2")
    assert row.status == "failed"
    assert row.error_message == "validation failed"
