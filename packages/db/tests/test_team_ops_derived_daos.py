"""S4 P4 — Derived cache DAO 单测。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
import pytest_asyncio
from devmanager_db.daos.team_ops.capacity_snapshot import CapacitySnapshotDAO
from devmanager_db.daos.team_ops.familiarity_edge import (
    FamiliarityEdgeDAO,
    compute_score,
)
from devmanager_db.daos.team_ops.iteration import IterationDAO
from devmanager_db.daos.team_ops.workload_snapshot import WorkloadSnapshotDAO
from devmanager_db.models import (
    CapacitySnapshot,
    FamiliarityEdge,
    Iteration,
    WorkloadSnapshot,
)
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    yield
    # 任何失败后 session 处于 aborted 状态 → 先 rollback 再删
    await session.rollback()
    await session.execute(delete(WorkloadSnapshot))
    await session.execute(delete(CapacitySnapshot))
    await session.execute(delete(FamiliarityEdge))
    await session.execute(delete(Iteration))
    await session.commit()


# ── WorkloadSnapshotDAO ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workload_upsert_then_get(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = WorkloadSnapshotDAO(session)
    pid = uuid.uuid4()
    await dao.upsert(
        person_id=pid,
        time_window="7d",
        open_issues=3,
        in_progress_issues=2,
        completed_issues=5,
        estimate_hours_remaining=12.0,
        estimate_hours_completed=20.0,
    )
    row = await dao.get(pid, "7d")
    assert row is not None
    assert row.open_issues == 3
    assert row.estimate_hours_remaining == 12.0


@pytest.mark.asyncio
async def test_workload_upsert_idempotent(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = WorkloadSnapshotDAO(session)
    pid = uuid.uuid4()
    await dao.upsert(
        person_id=pid,
        time_window="30d",
        open_issues=1,
        in_progress_issues=1,
        completed_issues=1,
        estimate_hours_remaining=4.0,
        estimate_hours_completed=8.0,
    )
    # 二次 upsert：同 (person, window) 应覆盖而非新建
    await dao.upsert(
        person_id=pid,
        time_window="30d",
        open_issues=99,
        in_progress_issues=99,
        completed_issues=99,
        estimate_hours_remaining=999.0,
        estimate_hours_completed=999.0,
    )
    rows = await dao.list_by_window("30d")
    matched = [r for r in rows if r.person_id == pid]
    assert len(matched) == 1
    assert matched[0].open_issues == 99


@pytest.mark.asyncio
async def test_workload_rejects_invalid_window(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = WorkloadSnapshotDAO(session)
    with pytest.raises(Exception):  # CHECK constraint
        await dao.upsert(
            person_id=uuid.uuid4(),
            time_window="1y",
            open_issues=0,
            in_progress_issues=0,
            completed_issues=0,
            estimate_hours_remaining=0,
            estimate_hours_completed=0,
        )


# ── CapacitySnapshotDAO ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_capacity_upsert_computes_load_ratio(
    session: AsyncSession,
    cleanup: None,
) -> None:
    # capacity_snapshot.iteration_id 有 FK → 先建一个真实 iteration
    it = await IterationDAO(session).upsert_from_pm(
        pm_iteration_id=f"pm-cap-{uuid.uuid4().hex[:6]}",
        name="Cap Test",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 14),
        status="active",
    )
    dao = CapacitySnapshotDAO(session)
    pid = uuid.uuid4()
    # estimated=80, weekly=40, weeks=2 → load_ratio = 80/(40*2) = 1.0
    await dao.upsert(
        person_id=pid,
        iteration_id=it.iteration_id,
        estimated_hours=80.0,
        weekly_capacity_hours=40.0,
        iteration_weeks=2,
    )
    row = await dao.get(pid, it.iteration_id)
    assert row is not None
    assert row.load_ratio == 1.0


@pytest.mark.asyncio
async def test_capacity_overload_above_one(
    session: AsyncSession,
    cleanup: None,
) -> None:
    it = await IterationDAO(session).upsert_from_pm(
        pm_iteration_id=f"pm-cap-{uuid.uuid4().hex[:6]}",
        name="Overload Test",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 14),
        status="active",
    )
    dao = CapacitySnapshotDAO(session)
    pid = uuid.uuid4()
    # estimated=120, weekly=40, weeks=2 → load_ratio = 1.5
    await dao.upsert(
        person_id=pid,
        iteration_id=it.iteration_id,
        estimated_hours=120.0,
        weekly_capacity_hours=40.0,
        iteration_weeks=2,
    )
    row = await dao.get(pid, it.iteration_id)
    assert row is not None
    assert row.load_ratio == 1.5


# ── FamiliarityEdgeDAO ─────────────────────────────────────────────────────


def test_compute_score_diminishing_returns() -> None:
    """1000 行 vs 10 行：score 增长远小于 100×。"""
    s_small = compute_score(lines_changed=10, commits_count=1)
    s_large = compute_score(lines_changed=1000, commits_count=1)
    # log10(11) ≈ 1.04, log10(1001) ≈ 3.00, ratio ≈ 2.88
    assert s_large / s_small < 4.0  # 远小于线性 100×


@pytest.mark.asyncio
async def test_familiarity_upsert_score(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = FamiliarityEdgeDAO(session)
    pid = uuid.uuid4()
    await dao.upsert(
        person_id=pid,
        area_key="lang:python",
        commits_count=10,
        lines_changed=500,
    )
    edges = await dao.list_by_person(pid)
    assert len(edges) == 1
    assert edges[0].area_key == "lang:python"
    assert edges[0].score > 0


@pytest.mark.asyncio
async def test_familiarity_top_across_people(
    session: AsyncSession,
    cleanup: None,
) -> None:
    dao = FamiliarityEdgeDAO(session)
    for i, lines in enumerate([100, 500, 50, 800]):
        await dao.upsert(
            person_id=uuid.uuid4(),
            area_key="lang:python",
            commits_count=5,
            lines_changed=lines,
        )
    top = await dao.top_across_people(area_key="lang:python", limit=2)
    assert len(top) == 2
    # 第一名是 lines_changed=800
    assert top[0].lines_changed == 800
    assert top[1].lines_changed == 500
