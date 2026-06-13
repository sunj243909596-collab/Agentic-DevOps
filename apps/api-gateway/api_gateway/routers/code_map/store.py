"""In-memory store for code-map data.

Holds the current ScopeGraph for each scope plus a per-scope stale_streak
counter that powers the UI "最近 N 次未重生成功" yellow banner.
"""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from typing import Any

from .schema import ScopeGraph


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class CodeMapStore:
    def __init__(self) -> None:
        self._scopes: dict[str, ScopeGraph] = {}
        self._stale_streak: dict[str, int] = {}
        self._last_pull_at: str | None = None
        self._lock = Lock()

    def put(
        self,
        scope: str,
        graph: ScopeGraph,
        *,
        stale: bool = False,
        stale_reason: str | None = None,
    ) -> None:
        with self._lock:
            if stale:
                # Caller provided their own stale flag → use it
                graph = graph.model_copy(
                    update={
                        "stale": True,
                        "stale_reason": stale_reason or "unknown",
                    }
                )
                self._stale_streak[scope] = self._stale_streak.get(scope, 0) + 1
            else:
                graph = graph.model_copy(update={"stale": False, "stale_reason": None})
                self._stale_streak[scope] = 0
            self._scopes[scope] = graph
            self._last_pull_at = _now_iso()

    def get(self, scope: str) -> ScopeGraph | None:
        with self._lock:
            return self._scopes.get(scope)

    def all_graphs(self) -> list[ScopeGraph]:
        """Public enumeration of all in-memory scope graphs (a copy under lock)."""
        with self._lock:
            return list(self._scopes.values())

    def status(self) -> dict[str, Any]:
        with self._lock:
            scopes_out: dict[str, dict[str, Any]] = {}
            for name, g in self._scopes.items():
                scopes_out[name] = {
                    "version": g.version,
                    "head_sha": g.head_sha,
                    "stale": g.stale,
                    "stale_reason": g.stale_reason,
                    "stale_streak": self._stale_streak.get(name, 0),
                    "module_count": len(g.modules),
                }
            return {
                "last_pull_at": self._last_pull_at,
                "last_error": next(
                    (g.stale_reason for g in self._scopes.values() if g.stale),
                    None,
                ),
                "scopes": scopes_out,
            }
