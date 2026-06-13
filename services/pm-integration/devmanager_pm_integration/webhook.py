"""S4 P3 — PM 平台 webhook 接收端点（v1 disabled）。

按 A2 决策：自研平台不支持 webhook 推送，本路由仅留空架子以备 v2 启用。

启用方法：设置环境变量 `PM_WEBHOOK_ENABLED=true`。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_webhook_enabled() -> bool:
    """检查 webhook 是否启用。v1 默认 False。"""
    from devmanager_pm_integration.config import load_config

    try:
        return load_config().webhook_enabled
    except RuntimeError:
        return False


async def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """处理 PM 平台 webhook 推送。

    v1：未启用，调用方应在此之前先检查 `is_webhook_enabled()`。
    v2 实装：解析 payload → 触发增量同步 → 写 audit。
    """
    logger.warning(
        "PM webhook handler called but v1 is disabled; payload ignored. "
        "Set PM_WEBHOOK_ENABLED=true to enable."
    )
    return {
        "status": "disabled",
        "message": "v1 webhook handler is disabled. See PM_WEBHOOK_ENABLED.",
    }
