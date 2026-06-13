"""sync 层集成测试：mock PMClient + 真实 DB（pg agent_devops）。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
from devmanager_db.daos.team_ops.issue import IssueDAO
from devmanager_db.daos.team_ops.iteration import IterationDAO
from devmanager_db.models import (
    AuditEvent,
    Issue,
    IssueAssignment,
    Iteration,
    PmSyncCursor,
)
from devmanager_pm_integration.client import PMClient
from devmanager_pm_integration.config import PMIntegrationConfig
from devmanager_pm_integration.sync import run_full_sync, run_incremental_sync
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


def _cfg() -> PMIntegrationConfig:
    return PMIntegrationConfig(
        base_url="https://pm.test",
        api_token="x",
        timeout_seconds=5,
        page_size=10,
        webhook_enabled=False,
    )


def _handler(payloads_by_path: dict[str, list[dict[str, Any]]]):
    """构造 httpx.MockTransport handler，path → items 翻一页。"""

    def h(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        items = payloads_by_path.get(path, [])
        return httpx.Response(200, json={"items": items, "next_cursor": None})

    return h


def _client_with_handler(
    cfg: PMIntegrationConfig,
    payloads_by_path: dict[str, list[dict[str, Any]]],
) -> PMClient:
    handler = _handler(payloads_by_path)

    async def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=cfg.timeout_seconds,
            transport=httpx.MockTransport(handler),
        )

    return PMClient(cfg, max_retries=0, base_backoff_seconds=0, client_factory=factory)


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    yield
    # reverse-FK: assignment → issue → iteration; cursor; audit（部分）
    await session.execute(delete(IssueAssignment))
    await session.execute(delete(Issue))
    await session.execute(delete(Iteration))
    await session.execute(delete(PmSyncCursor))
    await session.execute(delete(AuditEvent).where(AuditEvent.tool == "pm-integration"))
    await session.commit()


# ── Full sync ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_sync_inserts_iterations_issues(
    session: AsyncSession,
    cleanup: None,
) -> None:
    cfg = _cfg()
    payloads = {
        "/iterations": [
            {
                "id": "pm-it-1",
                "name": "Sprint 1",
                "start_date": "2026-06-01",
                "end_date": "2026-06-14",
                "status": "active",
                "updated_at": "2026-06-01T00:00:00Z",
            },
        ],
        "/issues": [
            {
                "id": "pm-1",
                "key": "WMS-1",
                "title": "T1",
                "type": "task",
                "priority": "low",
                "status": "open",
                "iteration_id": "pm-it-1",
                "updated_at": "2026-06-01T00:00:00Z",
            },
            {
                "id": "pm-2",
                "key": "WMS-2",
                "title": "T2",
                "type": "bug",
                "priority": "high",
                "status": "open",
                "iteration_id": "pm-it-1",
                "updated_at": "2026-06-01T00:00:00Z",
            },
        ],
        "/issue_assignments": [],
        "/users": [],
    }
    client = _client_with_handler(cfg, payloads)

    async with client:
        result = await run_full_sync(session, client, actor="test.full")
    assert result["success"] is True
    assert result["stats"]["iterations"] == 1
    assert result["stats"]["issues"] == 2
    assert result["stats"]["assignments"] == 0

    # 写库校验
    it_dao = IterationDAO(session)
    is_dao = IssueDAO(session)
    it = await it_dao.get_by_pm_id("pm-it-1")
    assert it is not None
    issues = await is_dao.list_by_iteration(it.iteration_id)
    assert len(issues) == 2

    # audit 写入了
    res = await session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "integration.sync")
    )
    events = list(res.scalars().all())
    assert len(events) == 1
    assert events[0].event_metadata["sync_type"] == "full"
    assert events[0].event_metadata["source"] == "pm"
    assert events[0].event_metadata["success"] is True


# ── Incremental sync: cursor 写入 + 下一轮复用 ─────────────────────────────


@pytest.mark.asyncio
async def test_incremental_sync_writes_cursor(
    session: AsyncSession,
    cleanup: None,
) -> None:
    cfg = _cfg()
    payloads = {
        "/iterations": [
            {
                "id": "pm-it-1",
                "name": "S1",
                "start_date": "2026-06-01",
                "end_date": "2026-06-14",
                "status": "active",
                "updated_at": "2026-06-10T08:00:00+00:00",
            },
        ],
        "/issues": [],
        "/issue_assignments": [],
    }
    client = _client_with_handler(cfg, payloads)
    async with client:
        result = await run_incremental_sync(session, client, actor="test.incr")
    assert result["success"] is True

    # 游标写入了
    res = await session.execute(
        select(PmSyncCursor).where(PmSyncCursor.source_key == "pm:iterations")
    )
    row = res.scalar_one()
    assert row.cursor_value is not None
    assert "2026-06-10" in row.cursor_value
    assert row.last_synced_at is not None


@pytest.mark.asyncio
async def test_incremental_sync_uses_existing_cursor(
    session: AsyncSession,
    cleanup: None,
) -> None:
    """第二轮 incremental 拉取时，client 应收到 updated_after=上次游标。"""
    # 预置游标
    cursor_row = PmSyncCursor(
        source_key="pm:iterations",
        cursor_value="2026-06-01T00:00:00+00:00",
        last_synced_at=datetime(2026, 6, 1, 0, 0, 0),
    )
    session.add(cursor_row)
    await session.commit()

    received_params: list[dict[str, str]] = []

    def h(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/iterations":
            received_params.append(dict(request.url.params))
            return httpx.Response(200, json={"items": [], "next_cursor": None})
        return httpx.Response(200, json={"items": []})

    cfg = _cfg()

    async def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=cfg.timeout_seconds,
            transport=httpx.MockTransport(h),
        )

    client = PMClient(cfg, max_retries=0, base_backoff_seconds=0, client_factory=factory)

    async with client:
        await run_incremental_sync(session, client, actor="test")
    assert received_params, "handler not called"
    assert received_params[0].get("updated_after") == "2026-06-01T00:00:00+00:00"


# ── Webhook v1 disabled ────────────────────────────────────────────────────


def test_webhook_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PM_WEBHOOK_ENABLED", raising=False)
    monkeypatch.setenv("PM_API_BASE_URL", "https://x")
    monkeypatch.setenv("PM_API_TOKEN", "y")
    from devmanager_pm_integration.webhook import is_webhook_enabled

    assert is_webhook_enabled() is False
