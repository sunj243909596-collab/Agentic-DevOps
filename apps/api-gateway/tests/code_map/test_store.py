# apps/api-gateway/tests/code_map/test_store.py
from __future__ import annotations

from api_gateway.routers.code_map.schema import Module, ScopeGraph
from api_gateway.routers.code_map.store import CodeMapStore


def _graph(version: int = 1, modules: list[Module] | None = None) -> ScopeGraph:
    return ScopeGraph(
        scope="apps",
        version=version,
        generated_at="2026-06-09T12:00:00Z",
        head_sha="abc",
        generator="test",
        modules=modules or [Module(id="apps/web", path="apps/web", name="Web")],
    )


def test_store_initially_empty():
    s = CodeMapStore()
    assert s.get("apps") is None
    assert s.status()["scopes"] == {}
    assert s.status()["last_pull_at"] is None


def test_store_put_and_get():
    s = CodeMapStore()
    s.put("apps", _graph(1))
    got = s.get("apps")
    assert got is not None
    assert got.version == 1


def test_store_stale_streak_increments_on_stale_put():
    s = CodeMapStore()
    s.put("apps", _graph(1), stale=True, stale_reason="LLM timeout")
    s.put("apps", _graph(2), stale=True, stale_reason="again")
    status = s.status()
    assert status["scopes"]["apps"]["stale_streak"] == 2
    assert status["scopes"]["apps"]["stale"] is True
    assert status["scopes"]["apps"]["stale_reason"] == "again"


def test_store_stale_streak_resets_on_success():
    s = CodeMapStore()
    s.put("apps", _graph(1), stale=True, stale_reason="x")
    s.put("apps", _graph(2), stale=True, stale_reason="x")
    s.put("apps", _graph(3))  # success
    assert s.status()["scopes"]["apps"]["stale_streak"] == 0
    assert s.status()["scopes"]["apps"]["stale"] is False


def test_store_last_pull_at_updates_on_every_put():
    s = CodeMapStore()
    assert s.status()["last_pull_at"] is None
    s.put("apps", _graph(1))
    assert s.status()["last_pull_at"] is not None
    first = s.status()["last_pull_at"]
    s.put("agents", _graph(1, []))
    assert s.status()["last_pull_at"] >= first
