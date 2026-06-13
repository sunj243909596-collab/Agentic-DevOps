# apps/api-gateway/tests/code_map/test_schema.py
from __future__ import annotations

import pytest
from api_gateway.routers.code_map.schema import (
    DepEdge,
    Edge,
    IndexFile,
    InterfaceEntry,
    Module,
    ModuleCard,
    ScopeGraph,
)
from pydantic import ValidationError


def test_module_minimal_required_fields():
    m = Module(id="apps/web", path="apps/web", name="PC 前端")
    assert m.id == "apps/web"
    assert m.kind == "lib"  # default
    assert m.entry_points == []  # default
    assert m.key_files == []  # default


def test_module_rejects_empty_id():
    with pytest.raises(ValidationError):
        Module(id="", path="apps/web", name="X")


def test_edge_requires_from_and_to():
    e = Edge(**{"from": "a", "to": "b"})
    assert e.via is None
    e2 = Edge(**{"from": "a", "to": "b", "via": "a/imports/b.ts"})
    assert e2.via == "a/imports/b.ts"


def test_edge_accepts_from_underscore_via_populate_by_name():
    """`from` is a Python keyword; populate_by_name must also accept from_."""
    e = Edge(**{"from_": "a", "to": "b"})
    assert e.from_ == "a"
    assert e.to == "b"


def test_scope_graph_round_trip_json():
    g = ScopeGraph(
        scope="apps",
        version=3,
        generated_at="2026-06-09T12:00:00Z",
        head_sha="abc",
        generator="claude-opus-4-8",
        modules=[Module(id="apps/web", path="apps/web", name="Web")],
        edges=[],
    )
    js = g.model_dump_json()
    g2 = ScopeGraph.model_validate_json(js)
    assert g2 == g


def test_module_card_consumes_api_format():
    c = ModuleCard(
        scope="apps",
        module_id="apps/web",
        version=1,
        generated_at="2026-06-09T12:00:00Z",
        head_sha="abc",
        responsibility="Vue SPA",
        interfaces=InterfaceEntry(
            exports=["App"],
            imports=["@/api"],
            consumes_api=["GET /v1/settings"],
        ),
        depends_on=[DepEdge(id="apps/api/contracts", kind="TypeScript types")],
        depended_on_by=[DepEdge(id="agents/manager-agent", kind="REST calls")],
        key_files=[],
        notes="",
    )
    assert c.interfaces.consumes_api == ["GET /v1/settings"]
    assert c.depends_on[0].id == "apps/api/contracts"
    assert c.depended_on_by[0].kind == "REST calls"


def test_module_card_round_trip_json():
    c = ModuleCard(
        scope="apps",
        module_id="apps/web",
        version=2,
        generated_at="2026-06-09T12:00:00Z",
        head_sha="abc",
        responsibility="Vue SPA",
        interfaces=InterfaceEntry(exports=["App"], consumes_api=["GET /v1/settings"]),
        depends_on=[DepEdge(id="apps/api/contracts", kind="types")],
        depended_on_by=[],
        key_files=["apps/web/src/main.tsx"],
        notes="改 API 需同步改 client.ts",
    )
    js = c.model_dump_json()
    c2 = ModuleCard.model_validate_json(js)
    assert c2 == c
    assert c2.notes == "改 API 需同步改 client.ts"


def test_index_file_default_scopes_is_empty_dict():
    idx = IndexFile(generated_at="2026-06-09T12:00:00Z", last_pull_at="2026-06-09T12:00:00Z")
    assert idx.scopes == {}
    assert idx.last_error is None
