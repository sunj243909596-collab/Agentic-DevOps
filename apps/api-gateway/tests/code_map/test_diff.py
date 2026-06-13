# apps/api-gateway/tests/code_map/test_diff.py
from __future__ import annotations

from api_gateway.routers.code_map.diff import diff_scope_graphs
from api_gateway.routers.code_map.schema import Edge, Module, ScopeGraph


def _g(modules: list[Module], edges: list[Edge] | None = None, version: int = 1) -> ScopeGraph:
    return ScopeGraph(
        scope="apps",
        version=version,
        generated_at="2026-06-09T12:00:00Z",
        head_sha="abc",
        generator="test",
        modules=modules,
        edges=edges or [],
    )


def test_diff_added_module():
    a = _g([Module(id="apps/web", path="apps/web", name="Web")])
    b = _g(
        [
            Module(id="apps/web", path="apps/web", name="Web"),
            Module(id="apps/api", path="apps/api", name="API"),
        ]
    )
    d = diff_scope_graphs(a, b)
    assert len(d["added_modules"]) == 1
    assert d["added_modules"][0].id == "apps/api"
    assert d["removed_modules"] == []


def test_diff_removed_module():
    a = _g(
        [
            Module(id="apps/web", path="apps/web", name="Web"),
            Module(id="apps/api", path="apps/api", name="API"),
        ]
    )
    b = _g([Module(id="apps/web", path="apps/web", name="Web")])
    d = diff_scope_graphs(a, b)
    assert len(d["removed_modules"]) == 1
    assert d["removed_modules"][0].id == "apps/api"


def test_diff_changed_module_lists_fields():
    a = _g([Module(id="apps/web", path="apps/web", name="Web", responsibility="old")])
    b = _g([Module(id="apps/web", path="apps/web", name="Web", responsibility="new")])
    d = diff_scope_graphs(a, b)
    assert len(d["changed_modules"]) == 1
    assert "responsibility" in d["changed_modules"][0]["fields_changed"]


def test_diff_added_and_removed_edges():
    e_old = [Edge(**{"from": "a", "to": "b", "via": "a/imp/b.ts"})]
    e_new = [Edge(**{"from": "a", "to": "c", "via": "a/imp/c.ts"})]
    d = diff_scope_graphs(_g([], e_old), _g([], e_new))
    assert len(d["added_edges"]) == 1
    assert d["added_edges"][0].to == "c"
    assert len(d["removed_edges"]) == 1
    assert d["removed_edges"][0].to == "b"


def test_diff_meta_fields():
    a = _g([Module(id="x", path="x", name="X")], version=3)
    b = _g([Module(id="x", path="x", name="X")], version=4)
    d = diff_scope_graphs(a, b)
    assert d["from_version"] == 3
    assert d["to_version"] == 4
    assert d["scope"] == "apps"
