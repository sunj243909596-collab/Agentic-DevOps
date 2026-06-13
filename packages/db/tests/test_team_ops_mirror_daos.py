"""S4 P2 — Mirror DAO tests.

4 个 DAO: IterationDAO / IssueDAO / IssueAssignmentDAO / MrReviewEventDAO
清理策略：与 P1 一致（依赖外键 cascade，测试结束统一清表）
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from devmanager_db.daos.team_ops.issue import IssueDAO
from devmanager_db.daos.team_ops.issue_assignment import IssueAssignmentDAO
from devmanager_db.daos.team_ops.iteration import IterationDAO
from devmanager_db.daos.team_ops.mr_review_event import MrReviewEventDAO
from devmanager_db.models import (
    Issue,
    IssueAssignment,
    Iteration,
    MrReviewEvent,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    yield
    # reverse-FK: assignment → issue → iteration, mr_review_event 独立
    await session.execute(delete(IssueAssignment))
    await session.execute(delete(Issue))
    await session.execute(delete(Iteration))
    await session.execute(delete(MrReviewEvent))
    await session.commit()


# ── IterationDAO ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_iteration_upsert_creates_then_updates(session: AsyncSession, cleanup: None) -> None:
    dao = IterationDAO(session)
    pid = f"pm-it-{uuid.uuid4().hex[:8]}"

    first = await dao.upsert_from_pm(
        pm_iteration_id=pid,
        name="Sprint 1",
        start_date=datetime(2026, 6, 1),
        end_date=datetime(2026, 6, 14),
        status="planning",
    )
    assert first.iteration_id is not None

    # second upsert: same pm_iteration_id should update
    second = await dao.upsert_from_pm(
        pm_iteration_id=pid,
        name="Sprint 1 (renamed)",
        start_date=datetime(2026, 6, 1),
        end_date=datetime(2026, 6, 14),
        status="active",
    )
    assert second.iteration_id == first.iteration_id
    fetched = await dao.get_by_pm_id(pid)
    assert fetched is not None
    assert fetched.name == "Sprint 1 (renamed)"
    assert fetched.status == "active"


@pytest.mark.asyncio
async def test_iteration_list_by_status(session: AsyncSession, cleanup: None) -> None:
    dao = IterationDAO(session)
    await dao.upsert_from_pm(
        pm_iteration_id=f"a-{uuid.uuid4().hex[:6]}",
        name="A",
        start_date=datetime(2026, 6, 1),
        end_date=datetime(2026, 6, 14),
        status="active",
    )
    await dao.upsert_from_pm(
        pm_iteration_id=f"b-{uuid.uuid4().hex[:6]}",
        name="B",
        start_date=datetime(2026, 6, 15),
        end_date=datetime(2026, 6, 28),
        status="completed",
    )
    actives = await dao.list_by_status("active")
    assert len([it for it in actives if it.name == "A"]) == 1


# ── IssueDAO ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_upsert_links_to_iteration(session: AsyncSession, cleanup: None) -> None:
    it_dao = IterationDAO(session)
    is_dao = IssueDAO(session)
    it = await it_dao.upsert_from_pm(
        pm_iteration_id=f"it-{uuid.uuid4().hex[:6]}",
        name="Sprint",
        start_date=datetime(2026, 6, 1),
        end_date=datetime(2026, 6, 14),
        status="active",
    )
    issue = await is_dao.upsert_from_pm(
        pm_issue_id="42",
        issue_key="WMS-42",
        title="Implement X",
        issue_type="task",
        priority="high",
        status="in_progress",
        estimate_hours=8.0,
        iteration_id=it.iteration_id,
    )
    assert issue.iteration_id == it.iteration_id

    by_key = await is_dao.get_by_issue_key("WMS-42")
    assert by_key is not None
    assert by_key.estimate_hours == 8.0

    by_pid = await is_dao.get_by_pm_id("42")
    assert by_pid is not None
    assert by_pid.issue_id == issue.issue_id


@pytest.mark.asyncio
async def test_issue_list_by_iteration(session: AsyncSession, cleanup: None) -> None:
    it_dao = IterationDAO(session)
    is_dao = IssueDAO(session)
    it = await it_dao.upsert_from_pm(
        pm_iteration_id=f"it2-{uuid.uuid4().hex[:6]}",
        name="Sprint 2",
        start_date=datetime(2026, 7, 1),
        end_date=datetime(2026, 7, 14),
        status="active",
    )
    await is_dao.upsert_from_pm(
        pm_issue_id="1",
        issue_key="WMS-1",
        title="A",
        issue_type="task",
        priority="low",
        status="open",
        iteration_id=it.iteration_id,
    )
    await is_dao.upsert_from_pm(
        pm_issue_id="2",
        issue_key="WMS-2",
        title="B",
        issue_type="bug",
        priority="urgent",
        status="done",
        iteration_id=it.iteration_id,
    )

    open_issues = await is_dao.list_by_iteration(it.iteration_id, status="open")
    assert len(open_issues) == 1
    assert open_issues[0].title == "A"

    all_issues = await is_dao.list_by_iteration(it.iteration_id)
    assert len(all_issues) == 2


@pytest.mark.asyncio
async def test_issue_list_updated_since(session: AsyncSession, cleanup: None) -> None:
    is_dao = IssueDAO(session)
    cutoff = datetime.now(UTC)
    await is_dao.upsert_from_pm(
        pm_issue_id="old",
        issue_key="WMS-O",
        title="Old",
        issue_type="task",
        priority="low",
        status="open",
        pm_updated_at=cutoff - timedelta(days=1),
    )
    await is_dao.upsert_from_pm(
        pm_issue_id="new",
        issue_key="WMS-N",
        title="New",
        issue_type="task",
        priority="low",
        status="open",
        pm_updated_at=cutoff + timedelta(hours=1),
    )
    fresh = await is_dao.list_updated_since(cutoff)
    keys = {i.issue_key for i in fresh}
    assert "WMS-N" in keys
    assert "WMS-O" not in keys


# ── IssueAssignmentDAO ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_issue_assignment_upsert_unique_combo(session: AsyncSession, cleanup: None) -> None:
    is_dao = IssueDAO(session)
    a_dao = IssueAssignmentDAO(session)
    issue = await is_dao.upsert_from_pm(
        pm_issue_id="i1",
        issue_key="WMS-1",
        title="T",
        issue_type="task",
        priority="low",
        status="open",
    )

    # 第一次
    a1 = await a_dao.upsert_from_pm(
        issue_id=issue.issue_id,
        pm_user_id="u1",
        pm_username="alice",
        role="assignee",
        weight=0.6,
    )
    # 第二次：同 (issue, user, role) 应更新而非新建
    a2 = await a_dao.upsert_from_pm(
        issue_id=issue.issue_id,
        pm_user_id="u1",
        pm_username="alice_v2",
        role="assignee",
        weight=0.9,
    )
    assert a2.assignment_id == a1.assignment_id
    all_a = await a_dao.list_by_issue(issue.issue_id)
    assert len(all_a) == 1
    assert all_a[0].weight == 0.9
    assert all_a[0].pm_username == "alice_v2"


@pytest.mark.asyncio
async def test_issue_assignment_different_roles_coexist(
    session: AsyncSession, cleanup: None
) -> None:
    is_dao = IssueDAO(session)
    a_dao = IssueAssignmentDAO(session)
    issue = await is_dao.upsert_from_pm(
        pm_issue_id="i2",
        issue_key="WMS-2",
        title="T",
        issue_type="task",
        priority="low",
        status="open",
    )
    await a_dao.upsert_from_pm(
        issue_id=issue.issue_id,
        pm_user_id="u1",
        pm_username="alice",
        role="assignee",
    )
    await a_dao.upsert_from_pm(
        issue_id=issue.issue_id,
        pm_user_id="u1",
        pm_username="alice",
        role="reporter",
    )
    items = await a_dao.list_by_issue(issue.issue_id)
    assert len(items) == 2
    roles = {a.role for a in items}
    assert roles == {"assignee", "reporter"}


# ── MrReviewEventDAO ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mr_review_event_record_basic(session: AsyncSession, cleanup: None) -> None:
    dao = MrReviewEventDAO(session)
    evt = await dao.record(
        project_id=100,
        mr_iid=42,
        action="opened",
        event_created_at=datetime(2026, 6, 1, 10, 0, 0),
        author_gitlab_user_id=999,
        target_sha="a" * 40,
        source_branch="feature/x",
        target_branch="main",
        title="Add X",
        raw_payload={"x": 1},
    )
    assert evt is not None
    assert evt.event_id is not None


@pytest.mark.asyncio
async def test_mr_review_event_idempotency(session: AsyncSession, cleanup: None) -> None:
    """同一 (project, mr, action, time) 不应重复入库。"""
    dao = MrReviewEventDAO(session)
    ts = datetime(2026, 6, 1, 10, 0, 0)
    first = await dao.record(
        project_id=100,
        mr_iid=42,
        action="opened",
        event_created_at=ts,
    )
    assert first is not None
    second = await dao.record(
        project_id=100,
        mr_iid=42,
        action="opened",
        event_created_at=ts,
    )
    assert second is None  # 幂等：第二次返回 None


@pytest.mark.asyncio
async def test_mr_review_event_list_by_author(session: AsyncSession, cleanup: None) -> None:
    dao = MrReviewEventDAO(session)
    for i in range(3):
        await dao.record(
            project_id=200,
            mr_iid=i + 1,
            action="reviewed",
            event_created_at=datetime(2026, 6, i + 1, 12, 0, 0),
            author_gitlab_user_id=777,
        )
    # 另一个 author 不应混入
    await dao.record(
        project_id=200,
        mr_iid=99,
        action="reviewed",
        event_created_at=datetime(2026, 6, 10, 12, 0, 0),
        author_gitlab_user_id=888,
    )
    rows = await dao.list_by_author_gitlab(777)
    assert len(rows) == 3
    assert all(r.author_gitlab_user_id == 777 for r in rows)
