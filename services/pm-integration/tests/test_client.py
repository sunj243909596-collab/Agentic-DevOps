"""PMClient 单测：用 httpx.MockTransport 模拟 PM 平台 API。"""

from __future__ import annotations

import httpx
import pytest
from devmanager_pm_integration.client import (
    PMAuthError,
    PMClient,
    PMNotFoundError,
    PMRateLimitedError,
    PMServerError,
)
from devmanager_pm_integration.config import PMIntegrationConfig


def _cfg() -> PMIntegrationConfig:
    return PMIntegrationConfig(
        base_url="https://pm.test",
        api_token="secret-token",
        timeout_seconds=5,
        page_size=10,
        webhook_enabled=False,
    )


def _factory(cfg: PMIntegrationConfig, handler):
    """测试用 factory：mock transport + 真实 auth header。"""

    async def f() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=cfg.timeout_seconds,
            headers={
                "Authorization": f"Bearer {cfg.api_token}",
                "Accept": "application/json",
            },
            transport=httpx.MockTransport(handler),
        )

    return f


def _client(
    cfg: PMIntegrationConfig,
    handler,
    *,
    max_retries: int = 0,
) -> PMClient:
    return PMClient(
        cfg,
        max_retries=max_retries,
        base_backoff_seconds=0,
        client_factory=_factory(cfg, handler),
    )


# ── 200 happy path ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_json_200_returns_parsed_dict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-token"
        return httpx.Response(200, json={"id": "1", "name": "x"})

    client = _client(_cfg(), handler)
    async with client:
        data = await client.get_json("/iterations/1")
    assert data == {"id": "1", "name": "x"}


# ── 401 auth error ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_json_401_raises_auth_error_no_retry() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, text="unauthorized")

    client = _client(_cfg(), handler, max_retries=3)
    async with client:
        with pytest.raises(PMAuthError):
            await client.get_json("/iterations")
    assert call_count == 1  # 401 不重试


# ── 404 not found ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_json_404_raises_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    client = _client(_cfg(), handler, max_retries=3)
    async with client:
        with pytest.raises(PMNotFoundError):
            await client.get_json("/x/999")


# ── 429 rate limited: 重试到耗尽后抛错 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_json_429_retries_then_raises() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, text="slow down")

    client = _client(_cfg(), handler, max_retries=2)
    async with client:
        with pytest.raises(PMRateLimitedError):
            await client.get_json("/x")
    assert call_count == 3  # 1 initial + 2 retries


# ── 500 server error: 重试到耗尽后抛错 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_json_500_retries_then_raises() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="server error")

    client = _client(_cfg(), handler, max_retries=2)
    async with client:
        with pytest.raises(PMServerError):
            await client.get_json("/x")
    assert call_count == 3


# ── 500 → 200: 重试后成功 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_json_500_then_200_succeeds() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(500, text="oops")
        return httpx.Response(200, json={"ok": True})

    client = _client(_cfg(), handler, max_retries=3)
    async with client:
        data = await client.get_json("/x")
    assert data == {"ok": True}
    assert call_count == 2


# ── get_paginated: cursor 模式 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_paginated_cursor_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "1"}],
                    "next_cursor": "page2",
                },
            )
        if cursor == "page2":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "2"}],
                    "next_cursor": None,
                },
            )
        return httpx.Response(200, json={"items": []})

    client = _client(_cfg(), handler)
    async with client:
        items = await client.get_paginated("/issues")
    assert items == [{"id": "1"}, {"id": "2"}]


# ── get_paginated: offset 模式 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_paginated_offset_mode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "1"}, {"id": "2"}],
                    "total": 3,
                },
            )
        if page == 2:
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "3"}],
                    "total": 3,
                },
            )
        return httpx.Response(200, json={"items": [], "total": 3})

    client = _client(_cfg(), handler)
    async with client:
        items = await client.get_paginated("/issues")
    assert items == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
