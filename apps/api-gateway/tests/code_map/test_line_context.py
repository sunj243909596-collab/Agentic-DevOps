# apps/api-gateway/tests/code_map/test_line_context.py
from __future__ import annotations

from api_gateway.routers.code_map.line_context import find_module_for_file
from api_gateway.routers.code_map.schema import Module, ScopeGraph


def _graphs() -> list[ScopeGraph]:
    return [
        ScopeGraph(
            scope="apps",
            version=1,
            generated_at="t",
            head_sha="x",
            generator="t",
            modules=[
                Module(id="apps/web", path="apps/web", name="Web"),
                Module(id="apps/api", path="apps/api", name="API"),
                Module(id="apps/api/contracts", path="apps/api/contracts", name="Contracts"),
            ],
        ),
        ScopeGraph(
            scope="agents",
            version=1,
            generated_at="t",
            head_sha="x",
            generator="t",
            modules=[Module(id="agents/manager-agent", path="agents/manager-agent", name="Mgr")],
        ),
    ]


def test_longest_prefix_wins():
    result = find_module_for_file("apps/api/contracts/index.ts", _graphs())
    assert result is not None
    assert result["module_id"] == "apps/api/contracts"
    assert result["scope"] == "apps"


def test_falls_back_to_shallowest_match():
    result = find_module_for_file("apps/web/src/pages/Settings.tsx", _graphs())
    assert result["module_id"] == "apps/web"


def test_no_match_returns_none():
    result = find_module_for_file("unknown/path.ts", _graphs())
    assert result is None


def test_cross_scope_uses_path_not_scope_order():
    # apps/web is added before agents — make sure agents isn't picked
    result = find_module_for_file("agents/manager-agent/main.py", _graphs())
    assert result["scope"] == "agents"
    assert result["module_id"] == "agents/manager-agent"


def test_path_boundary_strict():
    # apps/web should not match apps/web-extra/...
    graphs = [
        ScopeGraph(
            scope="apps",
            version=1,
            generated_at="t",
            head_sha="x",
            generator="t",
            modules=[Module(id="apps/web", path="apps/web", name="Web")],
        )
    ]
    result = find_module_for_file("apps/web-extra/foo.ts", graphs)
    assert result is None  # NOT apps/web, because not a strict prefix
