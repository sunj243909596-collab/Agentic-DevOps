"""TDD tests for PMIntegrationConfig loading.

每个测试通过 monkeypatch 设置 env，跑完即恢复。
"""

from __future__ import annotations

import pytest
from devmanager_pm_integration.config import (
    PMIntegrationConfig,
    _strip_trailing_slash,
    load_config,
)

# ── _strip_trailing_slash 单元测试 ─────────────────────────────────────────


def test_strip_trailing_slash_removes_single_slash() -> None:
    assert _strip_trailing_slash("https://pm.example.com/") == "https://pm.example.com"


def test_strip_trailing_slash_keeps_no_slash() -> None:
    assert _strip_trailing_slash("https://pm.example.com") == "https://pm.example.com"


def test_strip_trailing_slash_removes_multiple_trailing_slashes() -> None:
    # rstrip 一次清掉全部末尾 /
    assert _strip_trailing_slash("https://pm.example.com///") == "https://pm.example.com"


# ── load_config 必填项 fail-fast ────────────────────────────────────────────


def test_load_config_missing_base_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PM_API_BASE_URL", raising=False)
    monkeypatch.setenv("PM_API_TOKEN", "dummy")
    with pytest.raises(RuntimeError, match="PM_API_BASE_URL is required"):
        load_config()


def test_load_config_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.delenv("PM_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="PM_API_TOKEN is required"):
        load_config()


def test_load_config_blank_values_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "   ")
    monkeypatch.setenv("PM_API_TOKEN", "dummy")
    with pytest.raises(RuntimeError, match="PM_API_BASE_URL is required"):
        load_config()


# ── load_config 数值校验 ────────────────────────────────────────────────────


def test_load_config_invalid_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.setenv("PM_API_TOKEN", "dummy")
    monkeypatch.setenv("PM_API_TIMEOUT_SECONDS", "not-an-int")
    with pytest.raises(RuntimeError, match="not a valid integer"):
        load_config()


def test_load_config_zero_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.setenv("PM_API_TOKEN", "dummy")
    monkeypatch.setenv("PM_API_TIMEOUT_SECONDS", "0")
    with pytest.raises(RuntimeError, match="must be positive"):
        load_config()


def test_load_config_negative_page_size_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.setenv("PM_API_TOKEN", "dummy")
    monkeypatch.setenv("PM_API_PAGE_SIZE", "-5")
    with pytest.raises(RuntimeError, match="must be positive"):
        load_config()


# ── load_config 默认值 ──────────────────────────────────────────────────────


def test_load_config_defaults_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.setenv("PM_API_TOKEN", "secret-token-xyz")
    monkeypatch.delenv("PM_API_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PM_API_PAGE_SIZE", raising=False)
    monkeypatch.delenv("PM_WEBHOOK_ENABLED", raising=False)
    cfg = load_config()
    assert cfg.base_url == "https://pm.example.com"
    assert cfg.timeout_seconds == 30
    assert cfg.page_size == 100
    assert cfg.webhook_enabled is False


# ── load_config 边界 / 解析 ────────────────────────────────────────────────


def test_load_config_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com/")
    monkeypatch.setenv("PM_API_TOKEN", "secret-token-xyz")
    cfg = load_config()
    assert cfg.base_url == "https://pm.example.com"


def test_load_config_webhook_enabled_parses_truthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.setenv("PM_API_TOKEN", "secret-token-xyz")
    monkeypatch.setenv("PM_WEBHOOK_ENABLED", "true")
    assert load_config().webhook_enabled is True


def test_load_config_webhook_enabled_parses_falsy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.setenv("PM_API_TOKEN", "secret-token-xyz")
    monkeypatch.setenv("PM_WEBHOOK_ENABLED", "no")
    assert load_config().webhook_enabled is False


# ── 关键安全：__repr__ 不泄漏 token ─────────────────────────────────────────


def test_repr_does_not_leak_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PM_API_BASE_URL", "https://pm.example.com")
    monkeypatch.setenv("PM_API_TOKEN", "super-secret-token-DO-NOT-LEAK")
    cfg = load_config()
    text = repr(cfg)
    assert "super-secret-token" not in text
    assert "DO-NOT-LEAK" not in text
    # 但其他字段应可见
    assert "https://pm.example.com" in text


def test_config_is_frozen() -> None:
    cfg = PMIntegrationConfig(
        base_url="https://pm.example.com",
        api_token="x",
        timeout_seconds=30,
        page_size=100,
        webhook_enabled=False,
    )
    with pytest.raises(Exception):  # FrozenInstanceError 或 AttributeError
        cfg.timeout_seconds = 60  # type: ignore[misc]
