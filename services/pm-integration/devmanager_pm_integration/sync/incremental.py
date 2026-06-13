"""S4 P3 — 增量同步。

每 1 小时触发：按 PM 平台 `updated_at` 拉取增量，按 pm_sync_cursor 记录水位线。
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from devmanager_db.daos.audit_event import AuditEventDAO
from devmanager_db.daos.team_ops.issue import IssueDAO
from devmanager_db.daos.team_ops.issue_assignment import IssueAssignmentDAO
from devmanager_db.daos.team_ops.iteration import IterationDAO
from devmanager_db.daos.team_ops.pm_identity import PmIdentityDAO
from devmanager_db.daos.team_ops.pm_sync_cursor import PmSyncCursorDAO
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_pm_integration.audit import record_sync
from devmanager_pm_integration.client import PMClient
from devmanager_pm_integration.sync.upsert import (
    upsert_assignments_batch,
    upsert_issues_batch,
    upsert_iterations_batch,
)

logger = logging.getLogger(__name__)


async def _cursor_or_default(
    cursor_dao: PmSyncCursorDAO, source_key: str,
) -> str | None:
    row = await cursor_dao.get(source_key)
    if row is None:
        return None
    return row.cursor_value


async def run_incremental_sync(
    session: AsyncSession,
    client: PMClient,
    *,
    actor: str = "pm-integration.incremental",
) -> dict[str, Any]:
    """执行一次增量同步。

    每资源：读 cursor → 拉 `?updated_after=<cursor>` → upsert → 更新 cursor = max(updated_at)。
    """
    started = time.monotonic()
    audit = AuditEventDAO(session)
    iteration_dao = IterationDAO(session)
    issue_dao = IssueDAO(session)
    assignment_dao = IssueAssignmentDAO(session)
    pm_identity_dao = PmIdentityDAO(session)
    cursor_dao = PmSyncCursorDAO(session)

    stats: dict[str, int] = {}
    missing_all: list[str] = []
    failure_reason: str | None = None
    new_cursors: dict[str, str] = {}

    try:
        # iterations
        cur = await _cursor_or_default(cursor_dao, "pm:iterations")
        params: dict[str, Any] = {}
        if cur:
            params["updated_after"] = cur
        items = await client.get_paginated("/iterations", params=params)
        n, missing = await upsert_iterations_batch(iteration_dao, items)
        stats["iterations"] = n
        missing_all.extend(missing)
        if items:
            new_cursors["pm:iterations"] = _max_updated_at(items)

        # issues
        cur = await _cursor_or_default(cursor_dao, "pm:issues")
        params = {"updated_after": cur} if cur else {}
        items = await client.get_paginated("/issues", params=params)
        n, missing = await upsert_issues_batch(issue_dao, iteration_dao, items)
        stats["issues"] = n
        missing_all.extend(missing)
        if items:
            new_cursors["pm:issues"] = _max_updated_at(items)

        # assignments
        cur = await _cursor_or_default(cursor_dao, "pm:assignments")
        params = {"updated_after": cur} if cur else {}
        items = await client.get_paginated("/issue_assignments", params=params)
        n, missing = await upsert_assignments_batch(
            assignment_dao, issue_dao, pm_identity_dao, items,
        )
        stats["assignments"] = n
        missing_all.extend(missing)
        if items:
            new_cursors["pm:assignments"] = _max_updated_at(items)

        # 提交游标
        for key, value in new_cursors.items():
            await cursor_dao.upsert(source_key=key, cursor_value=value)
    except Exception as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.exception("PM incremental sync failed")

    duration_ms = int((time.monotonic() - started) * 1000)
    records_processed = sum(stats.values())
    success = failure_reason is None

    await record_sync(
        audit,
        actor=actor,
        sync_type="incremental",
        source="pm",
        records_processed=records_processed,
        duration_ms=duration_ms,
        success=success,
        failure_reason=failure_reason,
        metadata={
            "stats": stats,
            "new_cursors": new_cursors,
            "missing_fields_sample": missing_all[:20],
        },
    )
    await session.commit()

    return {
        "success": success,
        "stats": stats,
        "new_cursors": new_cursors,
        "duration_ms": duration_ms,
        "failure_reason": failure_reason,
    }


def _max_updated_at(items: list[dict[str, Any]]) -> str:
    """从 items 中挑最大 updated_at（ISO8601 字符串）。"""
    candidates: list[datetime] = []
    for item in items:
        raw = item.get("updated_at")
        if not raw:
            continue
        try:
            # PM 平台可能用 'Z' 后缀，Pydantic v2 容忍
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            candidates.append(datetime.fromisoformat(raw))
        except ValueError:
            continue
    if not candidates:
        return datetime.now(UTC).isoformat()
    return max(candidates).isoformat()
