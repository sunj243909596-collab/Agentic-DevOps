"""capacity_snapshot 重算。

数据源：iteration (P2) + issue_assignment × issue.estimate_hours。
逻辑：对 (person, iteration) 计算 estimated_hours；load_ratio = est / (weekly × weeks)。
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from devmanager_db.daos.team_ops.capacity_snapshot import CapacitySnapshotDAO
from devmanager_db.daos.team_ops.iteration import IterationDAO
from devmanager_db.daos.team_ops.person import PersonDAO
from devmanager_db.models import Issue, IssueAssignment
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def recompute_capacity(
    session: AsyncSession,
    *,
    iteration_id: uuid.UUID | None = None,
    weekly_capacity_hours: float = 40.0,
) -> dict[str, Any]:
    """重算 capacity_snapshot。

    - iteration_id=None → 重算所有 active iteration 的快照
    - iteration_id=具体值 → 只重算该 iteration
    - weekly_capacity_hours：v1 写死 40（P5+ 可从 setting 读）

    返回 stats：{ iterations: int, persons: int, overload_count: int }
    """
    iteration_dao = IterationDAO(session)
    person_dao = PersonDAO(session)

    if iteration_id is not None:
        it_row = await iteration_dao.get_by_id(iteration_id)
        iterations = [it_row] if it_row is not None else []
    else:
        iterations = await iteration_dao.list_active()

    persons = await person_dao.list_active()
    dao = CapacitySnapshotDAO(session)
    stats = {"iterations": 0, "persons": 0, "overload_count": 0}

    for it in iterations:
        weeks = _weeks_between(it.start_date, it.end_date)
        for person in persons:
            estimated = await _estimated_hours_for(
                session, person_id=person.person_id, iteration_id=it.iteration_id,
            )
            await dao.upsert(
                person_id=person.person_id,
                iteration_id=it.iteration_id,
                estimated_hours=estimated,
                weekly_capacity_hours=weekly_capacity_hours,
                iteration_weeks=weeks,
            )
            stats["persons"] += 1
            if weekly_capacity_hours > 0 and weeks > 0:
                if estimated / (weekly_capacity_hours * weeks) > 1.0:
                    stats["overload_count"] += 1
        stats["iterations"] += 1

    await session.commit()
    return stats


async def _estimated_hours_for(
    session: AsyncSession, *, person_id: uuid.UUID, iteration_id: uuid.UUID,
) -> float:
    """单个 person 在某个 iteration 内被分配 issue 的 estimate_hours 之和。"""
    result = await session.execute(
        select(func.coalesce(func.sum(Issue.estimate_hours), 0.0))
        .join(IssueAssignment, IssueAssignment.issue_id == Issue.issue_id)
        .where(
            IssueAssignment.person_id == person_id,
            Issue.iteration_id == iteration_id,
        )
    )
    return float(result.scalar_one() or 0.0)


def _weeks_between(start: date, end: date) -> int:
    """迭代周数：v1 用 (end - start).days // 7，最少 1 周。"""
    days = (end - start).days
    if days <= 0:
        return 1
    return max(1, days // 7)
