"""workload_snapshot 重算。

数据源：issue_assignment (P2) JOIN issues (P2) JOIN iteration (P2)。
逻辑：按 person_id × time_window 聚合。
- '7d' / '30d' 视为"最近 N 天内 pm_updated_at 的 issue"
- 'all' 视为全量
- in_progress / open / done 视 PM 平台 status 字面值而定（v1 简化：'open' | 'in_progress' | 'done'）
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from devmanager_db.daos.team_ops.person import PersonDAO
from devmanager_db.daos.team_ops.workload_snapshot import WorkloadSnapshotDAO
from devmanager_db.models import Issue, IssueAssignment
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


def _window_to_timedelta(window: str) -> timedelta | None:
    if window == "7d":
        return timedelta(days=7)
    if window == "30d":
        return timedelta(days=30)
    return None  # 'all' → no time filter


async def recompute_workload(
    session: AsyncSession,
    *,
    time_window: str = "7d",
) -> dict[str, Any]:
    """重算 workload_snapshot 全部 person 在指定 time_window 的行。

    返回 stats：{ persons: int, open: int, in_progress: int, completed: int }
    """
    if time_window not in ("7d", "30d", "all"):
        raise ValueError(f"time_window must be one of 7d/30d/all, got {time_window!r}")

    dao = WorkloadSnapshotDAO(session)
    person_dao = PersonDAO(session)
    persons = await person_dao.list_active()

    td = _window_to_timedelta(time_window)
    cutoff = datetime.now(UTC) - td if td is not None else None

    stats = {"persons": 0, "open": 0, "in_progress": 0, "completed": 0}

    for person in persons:
        # JOIN issues via issue_assignment，按 person_id 过滤；按 status 聚合
        rows = await _aggregate_for_person(
            session, person_id=person.person_id, cutoff=cutoff,
        )
        await dao.upsert(
            person_id=person.person_id,
            time_window=time_window,
            open_issues=rows["open"],
            in_progress_issues=rows["in_progress"],
            completed_issues=rows["completed"],
            estimate_hours_remaining=rows["est_remaining"],
            estimate_hours_completed=rows["est_completed"],
        )
        stats["persons"] += 1
        stats["open"] += rows["open"]
        stats["in_progress"] += rows["in_progress"]
        stats["completed"] += rows["completed"]

    await session.commit()
    return stats


async def _aggregate_for_person(
    session: AsyncSession, *, person_id: uuid.UUID, cutoff: datetime | None,
) -> dict[str, Any]:
    """对单个 person 聚合 open / in_progress / done 计数与 estimate 小时数。

    v1 简化：issue_assignment 行的 issue 状态。v2 可按权重加权。
    """
    # 一次性拉所有相关 issue_assignment（带 issue 关系）
    stmt = (
        select(Issue.status, Issue.estimate_hours)
        .join(IssueAssignment, IssueAssignment.issue_id == Issue.issue_id)
        .where(IssueAssignment.person_id == person_id)
    )
    if cutoff is not None:
        stmt = stmt.where(Issue.pm_updated_at >= cutoff)
    result = await session.execute(stmt)
    rows = result.all()

    out = {"open": 0, "in_progress": 0, "completed": 0,
           "est_remaining": 0.0, "est_completed": 0.0}
    for status, est in rows:
        est_val = float(est) if est is not None else 0.0
        s = (status or "").lower()
        if s in ("open", "todo", "backlog"):
            out["open"] += 1
            out["est_remaining"] += est_val
        elif s in ("in_progress", "doing", "review"):
            out["in_progress"] += 1
            out["est_remaining"] += est_val
        elif s in ("done", "closed", "resolved", "merged"):
            out["completed"] += 1
            out["est_completed"] += est_val
    return out


# suppress unused-import warning (func kept for v2 aggregation queries)
_ = func
