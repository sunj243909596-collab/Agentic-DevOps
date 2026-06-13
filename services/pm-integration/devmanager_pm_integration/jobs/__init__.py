"""S4 P3 — ARQ job wrappers。

供 apps/worker 或外部 cron 调用。worker 自己维护 connection pool，
本模块只提供任务函数（无状态）。
"""

from __future__ import annotations

import logging
from typing import Any

from devmanager_pm_integration.client import PMClient
from devmanager_pm_integration.config import load_config
from devmanager_pm_integration.sync import run_full_sync, run_incremental_sync

logger = logging.getLogger(__name__)


async def pm_full_sync_job(ctx: dict[str, Any]) -> dict[str, Any]:
    """ARQ job: 全量同步。

    期望 ctx 含 `session_factory`（async callable → AsyncSession）。
    ARQ 标准做法是 worker 在 startup 时往 ctx 注入。
    """
    session_factory = ctx.get("session_factory")
    if session_factory is None:
        raise RuntimeError("ctx.session_factory is required (ARQ worker startup hook)")

    cfg = load_config()
    async with session_factory() as session:
        async with PMClient(cfg) as client:
            return await run_full_sync(session, client, actor="arq.pm_full_sync")


async def pm_incremental_sync_job(ctx: dict[str, Any]) -> dict[str, Any]:
    """ARQ job: 增量同步。"""
    session_factory = ctx.get("session_factory")
    if session_factory is None:
        raise RuntimeError("ctx.session_factory is required (ARQ worker startup hook)")

    cfg = load_config()
    async with session_factory() as session:
        async with PMClient(cfg) as client:
            return await run_incremental_sync(
                session,
                client,
                actor="arq.pm_incremental_sync",
            )
