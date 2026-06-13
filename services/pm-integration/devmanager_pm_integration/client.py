"""自研需求平台 HTTP 客户端。

设计原则：
- **token 来自 env**（`config.api_token`），绝不硬编码
- **retry**：3 次指数退避；429 尊重 `Retry-After`；5xx 重试；401/4xx 立即失败
- **超时**：每次请求用 config.timeout_seconds
- **可测**：客户端可注入 `httpx.MockTransport` 用于测试
- **不可恢复错误 → 抛 `PMClientError` 子类**，不静默吞掉
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from devmanager_pm_integration.config import PMIntegrationConfig

logger = logging.getLogger(__name__)


# ── 异常 ────────────────────────────────────────────────────────────────────


class PMClientError(RuntimeError):
    """PM 平台 API 不可恢复错误的基类。"""


class PMAuthError(PMClientError):
    """401 / 403：token 无效或权限不足。不重试。"""


class PMNotFoundError(PMClientError):
    """404：资源不存在。不重试。"""


class PMRateLimitedError(PMClientError):
    """429：客户端已重试至耗尽。"""


class PMServerError(PMClientError):
    """5xx：服务端持续错误。"""


# ── 客户端 ──────────────────────────────────────────────────────────────────


def _default_client_factory(
    config: PMIntegrationConfig,
) -> Callable[[], Awaitable[httpx.AsyncClient]]:
    """默认工厂：构造标准 httpx.AsyncClient（带认证头）。"""

    async def _factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            headers={
                "Authorization": f"Bearer {config.api_token}",
                "Accept": "application/json",
                "User-Agent": "DevManager-Agent/pm-integration/0.1",
            },
        )

    return _factory


class PMClient:
    """自研需求平台 HTTP 客户端。"""

    def __init__(
        self,
        config: PMIntegrationConfig,
        *,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.5,
        client_factory: Callable[[], Awaitable[httpx.AsyncClient]] | None = None,
    ) -> None:
        self._config = config
        self._max_retries = max(0, max_retries)
        self._base_backoff = max(0.0, base_backoff_seconds)
        self._client_factory = client_factory or _default_client_factory(config)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PMClient:
        self._client = await self._client_factory()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── 公共方法 ───────────────────────────────────────────────────────────

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET → JSON dict。"""
        response = await self._request("GET", path, params=params)
        return self._parse_json(response)

    async def get_paginated(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """GET 翻页：cursor 优先，失败回退 offset 翻页。返回所有 items 列表。

        PM 平台分页响应假设（best-effort）：
        - cursor 模式：`{"items": [...], "next_cursor": str|None}`
        - offset 模式：`{"items": [...], "total": int, "page": int, "page_size": int}`

        翻完所有页后返回 items 列表（不含 next_cursor）。
        """
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        page = 1
        page_size = self._config.page_size
        base_params: dict[str, Any] = dict(params or {})

        while True:
            page_params = dict(base_params)
            if cursor is not None:
                page_params["cursor"] = cursor
            else:
                page_params["page"] = page
                page_params["page_size"] = page_size

            response = await self._request("GET", path, params=page_params)
            payload = self._parse_json(response)
            page_items = payload.get("items", [])
            if not isinstance(page_items, list):
                raise PMClientError(
                    f"PM API {path}: expected 'items' to be list, got {type(page_items).__name__}"
                )
            items.extend(page_items)

            cursor = payload.get("next_cursor")
            if cursor:
                continue  # 继续 cursor 翻页
            # 翻完一遍？看 total / page_size
            total = payload.get("total")
            if isinstance(total, int) and len(items) < total:
                page += 1
                continue
            break

        return items

    # ── 内部 ───────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise PMClientError("PMClient must be used via 'async with'")
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = path if path.startswith("/") else f"/{path}"

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                )
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    raise PMClientError(
                        f"PM API {method} {url} timed out after {self._max_retries + 1} attempts"
                    ) from exc
                await self._sleep(attempt, retry_after=None)
                continue
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt == self._max_retries:
                    raise PMClientError(f"PM API {method} {url} transport error: {exc}") from exc
                await self._sleep(attempt, retry_after=None)
                continue

            status = response.status_code
            if 200 <= status < 300:
                return response
            if status in (401, 403):
                raise PMAuthError(f"PM API {method} {url} auth failed ({status})")
            if status == 404:
                raise PMNotFoundError(f"PM API {method} {url} not found")
            if status == 429:
                retry_after = self._parse_retry_after(response)
                if attempt < self._max_retries:
                    await self._sleep(attempt, retry_after=retry_after)
                    continue
                raise PMRateLimitedError(
                    f"PM API {method} {url} rate limited after {self._max_retries + 1} attempts"
                )
            if 500 <= status < 600:
                if attempt < self._max_retries:
                    logger.warning(
                        "PM API %s %s returned %d, retrying (attempt %d)",
                        method,
                        url,
                        status,
                        attempt + 1,
                    )
                    await self._sleep(attempt, retry_after=None)
                    continue
                raise PMServerError(f"PM API {method} {url} server error {status}")
            # 其他 4xx（422/400 等）不重试
            raise PMClientError(f"PM API {method} {url} returned {status}: {response.text[:200]}")

        # 不应到达；保险起见
        raise PMClientError(f"PM API {method} {url} failed: {last_exc}")

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except Exception as exc:
            raise PMClientError(f"PM API returned non-JSON: {response.text[:200]}") from exc
        if not isinstance(data, dict):
            raise PMClientError(f"PM API expected JSON object, got {type(data).__name__}")
        return data

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        header = response.headers.get("Retry-After")
        if not header:
            return None
        try:
            return float(header)
        except ValueError:
            return None

    async def _sleep(self, attempt: int, *, retry_after: float | None) -> None:
        if retry_after is not None and retry_after > 0:
            await asyncio.sleep(retry_after)
            return
        backoff = self._base_backoff * (2**attempt)
        jitter = random.uniform(0, self._base_backoff)
        await asyncio.sleep(backoff + jitter)
