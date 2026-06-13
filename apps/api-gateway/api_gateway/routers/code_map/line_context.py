"""File → module lookup using longest-prefix matching.

Used by the /line-context endpoint and the Changes tab to label each
changed file with its owning module card.
"""
from __future__ import annotations

from typing import Any

from .schema import ScopeGraph


def find_module_for_file(
    file_path: str, scope_graphs: list[ScopeGraph]
) -> dict[str, Any] | None:
    """Return the module whose `path` is the longest strict prefix of `file_path`.

    Strict means: file_path must be `module.path + "/" + ...`, so that
    `apps/web` does NOT match `apps/web-extra/foo.ts`.

    Returns None if no module matches.
    """
    best: tuple[int, dict[str, Any]] | None = None
    for graph in scope_graphs:
        for m in graph.modules:
            prefix = m.path + "/"
            if file_path.startswith(prefix) or file_path == m.path:
                if best is None or len(m.path) > best[0]:
                    best = (len(m.path), {
                        "module_id": m.id,
                        "scope": graph.scope,
                        "responsibility": m.responsibility,
                        "kind": m.kind,
                    })
    return best[1] if best else None
