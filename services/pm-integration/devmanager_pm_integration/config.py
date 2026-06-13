"""PM integration configuration loaded from environment.

设计原则：
- 必填项缺失 → 启动 fail-fast (RuntimeError)，不在运行时静默 fallback
- 末尾斜杠统一去除（避免 PM_API_BASE_URL/a + PM_API_BASE_URL/a/ 出现双形态）
- token 永远只来自 env，绝不写入日志
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _read_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"Env var {name}={raw!r} is not a valid integer") from exc


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class PMIntegrationConfig:
    """自研需求平台集成配置。"""

    base_url: str
    api_token: str
    timeout_seconds: int
    page_size: int
    webhook_enabled: bool

    def __repr__(self) -> str:
        # 关键：api_token 永远不出现在 __repr__
        return (
            f"PMIntegrationConfig(base_url={self.base_url!r}, "
            f"timeout_seconds={self.timeout_seconds}, "
            f"page_size={self.page_size}, "
            f"webhook_enabled={self.webhook_enabled})"
        )


def _strip_trailing_slash(url: str) -> str:
    return url.rstrip("/") if url.endswith("/") else url


def load_config() -> PMIntegrationConfig:
    """从环境变量加载配置。缺失必填项时抛 RuntimeError。"""
    base_url = _read_str("PM_API_BASE_URL")
    if not base_url:
        raise RuntimeError(
            "PM_API_BASE_URL is required. Set it in .env or environment. "
            "Example: PM_API_BASE_URL=https://pm.example.com"
        )

    api_token = _read_str("PM_API_TOKEN")
    if not api_token:
        raise RuntimeError(
            "PM_API_TOKEN is required. Set it in .env or secrets manager. "
            "Do NOT hardcode tokens in source."
        )

    timeout_seconds = _read_int("PM_API_TIMEOUT_SECONDS", default=30)
    if timeout_seconds <= 0:
        raise RuntimeError(f"PM_API_TIMEOUT_SECONDS must be positive, got {timeout_seconds}")

    page_size = _read_int("PM_API_PAGE_SIZE", default=100)
    if page_size <= 0:
        raise RuntimeError(f"PM_API_PAGE_SIZE must be positive, got {page_size}")

    webhook_enabled = _read_bool("PM_WEBHOOK_ENABLED", default=False)

    return PMIntegrationConfig(
        base_url=_strip_trailing_slash(base_url),
        api_token=api_token,
        timeout_seconds=timeout_seconds,
        page_size=page_size,
        webhook_enabled=webhook_enabled,
    )
