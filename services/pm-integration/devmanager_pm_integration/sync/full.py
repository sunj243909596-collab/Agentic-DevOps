"""S4 P3 — 全量同步。

每日 02:00 触发（CRON 配置在 P9 / arq worker 处）。
覆盖：iterations / issues / assignments / users。
"""

from __future__ import annotations

import logging
import time
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


async def run_full_sync(
    session: AsyncSession,
    client: PMClient,
    *,
    actor: str = "pm-integration.full",
) -> dict[str, Any]:
    """执行一次全量同步。

    流程：
    1. 拉取 active iterations → upsert
    2. 拉取全部 open issues → upsert
    3. 拉取 issue assignments → upsert（两阶段解析 issue / person）
    4. 拉取 users（v1 不直接落库，留 audit）
    5. 写 integration.sync audit 事件
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

    try:
        iterations = await client.get_paginated("/iterations", params={"status": "active"})
        n, missing = await upsert_iterations_batch(iteration_dao, iterations)
        stats["iterations"] = n
        missing_all.extend(missing)

        # 全量 issue：拉所有 status（PM 平台一般 list_all 即可）
        issues = await client.get_paginated("/issues", params={"status": "open"})
        n, missing = await upsert_issues_batch(issue_dao, iteration_dao, issues)
        stats["issues"] = n
        missing_all.extend(missing)

        # assignments：通过 issue 列表逐 issue 拉（v1 简化：拉全部，PM 平台可能也提供 list_all）
        assignments = await client.get_paginated("/issue_assignments")
        n, missing = await upsert_assignments_batch(
            assignment_dao,
            issue_dao,
            pm_identity_dao,
            assignments,
        )
        stats["assignments"] = n
        missing_all.extend(missing)

        # users：v1 仅 audit 占位（person 由 CLI 创建）
        users = await client.get_paginated("/users")
        stats["users"] = len(users)

        # 重置游标
        for src in ("iterations", "issues", "assignments", "users"):
            await cursor_dao.upsert(source_key=f"pm:{src}", cursor_value=None)
    except Exception as exc:
        failure_reason = f"{type(exc).__name__}: {exc}"
        logger.exception("PM full sync failed")

    duration_ms = int((time.monotonic() - started) * 1000)
    records_processed = sum(stats.values())
    success = failure_reason is None

    await record_sync(
        audit,
        actor=actor,
        sync_type="full",
        source="pm",
        records_processed=records_processed,
        duration_ms=duration_ms,
        success=success,
        failure_reason=failure_reason,
        metadata={
            "stats": stats,
            "missing_fields_sample": missing_all[:20],
            "missing_fields_total": len(missing_all),
        },
    )
    await session.commit()

    return {
        "success": success,
        "stats": stats,
        "missing_fields_total": len(missing_all),
        "duration_ms": duration_ms,
        "failure_reason": failure_reason,
    }
