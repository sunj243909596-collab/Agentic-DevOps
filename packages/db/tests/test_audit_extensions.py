"""S4 P5 — audit_extensions helper 集成测试。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from devmanager_db.daos.audit_event import AuditEventDAO
from devmanager_db.daos.audit_extensions import (
    EVENT_SUGGESTION_FEEDBACK,
    EVENT_SUGGESTION_GENERATED,
    EVENT_SUGGESTION_VIEWED,
    record_suggestion_feedback,
    record_suggestion_generated,
    record_suggestion_viewed,
)
from devmanager_db.daos.team_ops.suggestion import SuggestionDAO
from devmanager_db.models import AuditEvent, Suggestion
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    yield
    await session.rollback()
    await session.execute(
        delete(AuditEvent).where(
            AuditEvent.event_type.in_(
                [
                    EVENT_SUGGESTION_GENERATED,
                    EVENT_SUGGESTION_VIEWED,
                    EVENT_SUGGESTION_FEEDBACK,
                ]
            )
        )
    )
    await session.execute(delete(Suggestion))
    await session.commit()


@pytest.mark.asyncio
async def test_record_suggestion_generated_writes_event(
    session: AsyncSession,
    cleanup: None,
) -> None:
    audit = AuditEventDAO(session)
    suggestion_id = uuid.uuid4()
    target_id = uuid.uuid4()

    await record_suggestion_generated(
        audit,
        actor="policy-engine",
        suggestion_id=suggestion_id,
        target_type="person",
        target_id=target_id,
        suggestion_type="sprint_planning",
        source_refs={"workload_snapshot_id": str(uuid.uuid4())},
    )

    res = await session.execute(
        select(AuditEvent).where(AuditEvent.event_type == EVENT_SUGGESTION_GENERATED)
    )
    events = list(res.scalars().all())
    assert len(events) == 1
    e = events[0]
    assert e.tool == "suggestion-engine"
    assert e.event_metadata["suggestion_id"] == str(suggestion_id)
    assert e.event_metadata["target_type"] == "person"
    assert e.event_metadata["suggestion_type"] == "sprint_planning"


@pytest.mark.asyncio
async def test_record_suggestion_viewed_and_feedback(
    session: AsyncSession,
    cleanup: None,
) -> None:
    # 先建一条 suggestion（实际业务流里 audit 会先有 generated 事件）
    s_dao = SuggestionDAO(session)
    s = await s_dao.create(
        target_type="person",
        target_id=uuid.uuid4(),
        suggestion_type="growth",
        payload={"facts": [], "trends": [], "notes": []},
    )

    audit = AuditEventDAO(session)
    await record_suggestion_viewed(
        audit,
        actor="alice",
        suggestion_id=s.suggestion_id,
    )
    await record_suggestion_feedback(
        audit,
        actor="alice",
        suggestion_id=s.suggestion_id,
        feedback_type="accepted",
        comment="useful",
    )

    res = await session.execute(
        select(AuditEvent).where(AuditEvent.event_type == EVENT_SUGGESTION_FEEDBACK)
    )
    events = list(res.scalars().all())
    assert len(events) == 1
    assert events[0].event_metadata["comment"] == "useful"

    res = await session.execute(
        select(AuditEvent).where(AuditEvent.event_type == EVENT_SUGGESTION_VIEWED)
    )
    viewed = list(res.scalars().all())
    assert len(viewed) == 1
