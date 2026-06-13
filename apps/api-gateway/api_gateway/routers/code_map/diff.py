"""Module-graph diff.

Compares two ScopeGraph instances and returns added/removed/changed modules
plus added/removed edges. Used by the UI Diff tab and the /diff endpoint.
"""
from __future__ import annotations

from typing import Any

from .schema import Edge, Module, ScopeGraph

_FIELDS_TO_COMPARE = ("name", "kind", "responsibility", "entry_points", "key_files")


def _edge_key(e: Edge) -> tuple[str, str, str | None]:
    return (e.from_, e.to, e.via)


def _module_fields_changed(a: Module, b: Module) -> list[str]:
    changed: list[str] = []
    for f in _FIELDS_TO_COMPARE:
        if getattr(a, f) != getattr(b, f):
            changed.append(f)
    return changed


def diff_scope_graphs(a: ScopeGraph, b: ScopeGraph) -> dict[str, Any]:
    a_modules = {m.id: m for m in a.modules}
    b_modules = {m.id: m for m in b.modules}

    added_ids   = set(b_modules) - set(a_modules)
    removed_ids = set(a_modules) - set(b_modules)
    common_ids  = set(a_modules) & set(b_modules)

    added_modules   = [b_modules[i] for i in sorted(added_ids)]
    removed_modules = [a_modules[i] for i in sorted(removed_ids)]
    changed_modules = []
    for mid in sorted(common_ids):
        fields = _module_fields_changed(a_modules[mid], b_modules[mid])
        if fields:
            changed_modules.append({
                "id": mid,
                "fields_changed": fields,
                "from": a_modules[mid].model_dump(),
                "to":   b_modules[mid].model_dump(),
            })

    a_edges = {_edge_key(e): e for e in a.edges}
    b_edges = {_edge_key(e): e for e in b.edges}
    added_edges   = [b_edges[k] for k in sorted(set(b_edges) - set(a_edges))]
    removed_edges = [a_edges[k] for k in sorted(set(a_edges) - set(b_edges))]

    return {
        "scope": b.scope,
        "from_version": a.version,
        "to_version": b.version,
        "added_modules": added_modules,
        "removed_modules": removed_modules,
        "changed_modules": changed_modules,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
    }
