"""Incremental regeneration of the code map.

Entry point: ``python -m api_gateway.routers.code_map.regen``

Triggered by ``scripts/pull.sh`` after ``git pull``. Detects changed files,
groups them by scope, asks the LLM for a new graph per affected scope,
writes the result to ``docs/code-map/``, and notifies the in-memory store.

Failure handling: any exception during one scope is caught, the old
graph is preserved, and the store is updated with ``stale=True``.
The CLI always exits 0 so a failed regen does not block the developer's
``git pull``.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from devmanager_llm import LLMAuthError, LLMProvider, run_complete

from .prompt import build_messages
from .schema import IndexFile, ModuleCard, ScopeGraph
from .store import CodeMapStore

log = logging.getLogger(__name__)

# Repository root: assume regen.py lives at apps/api-gateway/api_gateway/routers/code_map/regen.py
# code_map → routers → api_gateway → api-gateway → apps → REPO_ROOT
REPO_ROOT = Path(__file__).resolve().parents[5]
MAPS_DIR = REPO_ROOT / "docs" / "code-map"

# Transient retry policy: only network/timeout/5xx-class errors get a second
# chance. Auth / config / schema errors won't be cured by retrying.
TRANSIENT_RETRY_DELAY_SEC = 5
MAX_TRANSIENT_RETRIES = 1  # 1 retry = 2 total attempts per scope


# ── Error classification ─────────────────────────────────────────────────────

_TRANSIENT_KEYWORDS = (
    "timeout", "timed out", "connection", "reset by peer",
    "temporarily", "503", "502", "500", "504", "unavailable",
    "rate limit", "429", "overloaded",
)


def classify_error(exc: BaseException) -> str:
    """Return 'transient' for errors worth retrying, else 'permanent'.

    Permanent: LLMAuthError, pydantic ValidationError (schema mismatch), any
    other exception. Transient: built-in TimeoutError / ConnectionError,
    plus string-matches against `_TRANSIENT_KEYWORDS` (catches httpx,
    anthropic SDK, etc. wrapped exceptions).
    """
    if isinstance(exc, LLMAuthError):
        return "permanent"
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "transient"
    msg = str(exc).lower()
    if any(kw in msg for kw in _TRANSIENT_KEYWORDS):
        return "transient"
    return "permanent"


# ── Public helpers (testable) ─────────────────────────────────────────────────

def _get_changed_files(repo: str, prev_head: str, new_head: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", prev_head, new_head],
        cwd=repo, text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _group_by_scope(files: list[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for f in files:
        top = f.split("/", 1)[0]
        out.setdefault(top, set()).add(f)
    return out


def _collect_tree(scope: str, repo_root: Path, files: list[str], max_lines: int = 200) -> str:
    """Build a flat list of file paths for the scope, capped at max_lines."""
    scope_files = sorted(f for f in files if f.startswith(scope + "/") or f == scope)
    if len(scope_files) > max_lines:
        scope_files = scope_files[:max_lines] + [f"... (+{len(scope_files) - max_lines} more)"]
    return "\n".join(f"- {f}" for f in scope_files)


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ── Per-scope regeneration ───────────────────────────────────────────────────

def regen_one_scope(
    *,
    scope: str,
    old_graph: ScopeGraph | None,
    changed_files: list[str],
    file_tree: str,
    head_sha: str,
    provider: LLMProvider,
    store: CodeMapStore,
    maps_dir: Path | None = None,
    max_attempts: int = MAX_TRANSIENT_RETRIES + 1,
    sleep: callable = None,  # type: ignore[valid-type]
) -> None:
    """Regenerate one scope's graph. Transient errors are retried up to
    `max_attempts - 1` times with `TRANSIENT_RETRY_DELAY_SEC` between
    attempts; permanent errors fail immediately.

    `sleep` is injectable for tests; defaults to time.sleep.
    """
    if sleep is None:
        import time as _time
        sleep = _time.sleep

    maps_dir = maps_dir or MAPS_DIR
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            messages = build_messages(
                scope=scope,
                old_graph=old_graph,
                changed_files=sorted(changed_files),
                file_tree=file_tree,
                head_sha=head_sha,
                generator=provider.name,
            )
            response = run_complete(
                provider=provider,
                messages=messages, max_tokens=8192, temperature=0.0, system=None
            )
            # Parse LLM output — strip markdown fences if present
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.lower().startswith("json"):
                    text = text[4:]
                text = text.strip().rstrip("`").strip()
            new_graph = ScopeGraph.model_validate_json(text)
            # Bump version
            new_graph = new_graph.model_copy(update={
                "version": (old_graph.version + 1) if old_graph else 1,
                "stale": False, "stale_reason": None,
            })

            # Atomic write of the scope graph
            _atomic_write_json(
                maps_dir / f"{scope}.json",
                json.loads(new_graph.model_dump_json(exclude_none=True)),
            )

            # Per-module cards: write one file per module
            (maps_dir / scope).mkdir(parents=True, exist_ok=True)
            for m in new_graph.modules:
                card = ModuleCard(
                    scope=scope, module_id=m.id, version=new_graph.version,
                    generated_at=new_graph.generated_at, head_sha=new_graph.head_sha,
                    responsibility=m.responsibility,
                    interfaces={"exports": [], "imports": m.entry_points,
                                "consumes_api": [], "key_files": m.key_files},
                    key_files=m.key_files,
                )
                _atomic_write_json(
                    maps_dir / scope / f"{m.id.split('/')[-1]}.json",
                    json.loads(card.model_dump_json(exclude_none=True)),
                )

            # Update index
            _update_index(maps_dir, scope, new_graph)

            store.put(scope, new_graph)
            log.info("regen %s v%d OK (attempt %d)", scope, new_graph.version, attempt + 1)
            return

        except Exception as exc:
            last_exc = exc
            kind = classify_error(exc)
            if kind == "transient" and attempt < max_attempts - 1:
                log.warning(
                    "regen %s transient failure (attempt %d/%d): %s — retrying in %ds",
                    scope, attempt + 1, max_attempts, exc, TRANSIENT_RETRY_DELAY_SEC,
                )
                sleep(TRANSIENT_RETRY_DELAY_SEC)
                continue
            # Permanent or out of attempts — fall through to fallback
            break

    # Fallback: write a stale marker so the UI doesn't crash
    assert last_exc is not None
    log.warning("regen %s failed: %s — preserving old", scope, last_exc)
    if old_graph is not None:
        store.put(scope, old_graph, stale=True, stale_reason=str(last_exc))
    else:
        # No prior graph — write a placeholder so the UI doesn't crash
        placeholder = ScopeGraph(
            scope=scope, version=0,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            head_sha=head_sha, generator=provider.name,
            modules=[], edges=[], stale=True, stale_reason=str(last_exc),
        )
        store.put(scope, placeholder, stale=True, stale_reason=str(last_exc))


def _update_index(maps_dir: Path, scope: str, graph: ScopeGraph) -> None:
    idx_path = maps_dir / "index.json"
    if idx_path.exists():
        idx = IndexFile.model_validate_json(idx_path.read_text(encoding="utf-8"))
    else:
        idx = IndexFile(generated_at="t", last_pull_at=None)
    idx.generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    idx.last_pull_at = idx.generated_at
    idx.scopes[scope] = {
        "version": graph.version, "head_sha": graph.head_sha,
        "stale": graph.stale, "stale_reason": graph.stale_reason,
        "module_count": len(graph.modules),
    }
    _atomic_write_json(idx_path, json.loads(idx.model_dump_json(exclude_none=True)))


# ── CLI entrypoint ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate code map from git state")
    parser.add_argument("--prev-head", help="HEAD sha before pull（增量模式必填）")
    parser.add_argument("--new-head", help="HEAD sha after pull（增量模式必填）")
    parser.add_argument("--maps-dir", default=str(MAPS_DIR))
    parser.add_argument("--store-uri", default=os.getenv("CODE_MAP_STORE_URI", "memory"),
                        help="memory | redis://... (only memory implemented in v1)")
    parser.add_argument("--force-full", action="store_true",
                        help="忽略 git diff，对所有顶层目录全量重生")
    parser.add_argument("--scope", help="只重生指定 scope（可与 --force-full 配合，也可单独使用）")
    args = parser.parse_args(argv)

    maps_dir = Path(args.maps_dir)

    # Decide affected scopes
    if args.scope:
        by_scope = {args.scope: set()}
    elif args.force_full:
        # All top-level dirs (excluding special ones)
        skip = {".git", ".claude", "node_modules", "dist", ".venv",
                ".pytest_cache", ".logs", ".pids", "__pycache__"}
        by_scope = {
            d.name: set()
            for d in REPO_ROOT.iterdir()
            if d.is_dir() and d.name not in skip and not d.name.startswith(".")
        }
    else:
        # Incremental mode: require --prev-head/--new-head
        if not (args.prev_head and args.new_head):
            parser.error(
                "--prev-head 和 --new-head 在增量模式下必填；"
                "或使用 --force-full / --scope"
            )
        files = _get_changed_files(str(REPO_ROOT), args.prev_head, args.new_head)
        if not files:
            log.info("no changed files — skip regen")
            return 0
        by_scope = _group_by_scope(files)
    log.info("affected scopes: %s", list(by_scope))

    # Provider init
    try:
        from devmanager_llm import make_provider
        name = os.getenv("LLM_PROVIDER", "mock")
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL")
        base_url = os.getenv("LLM_BASE_URL")
        provider = make_provider(name, api_key=api_key, model=model, base_url=base_url)
    except LLMAuthError as exc:
        reason = "LLM 未配置"
        log.warning("LLM not configured: %s — writing fallback index", exc)
        print(
            f"code map 未初始化，请配置 LLM 后重试 ({reason})",
            file=sys.stderr,
        )
        _write_fallback_index(
            maps_dir, list(by_scope), reason, args.new_head or "HEAD",
        )
        return 0

    # Build in-memory store from current disk
    store = CodeMapStore()
    _load_disk_into_store(maps_dir, store)

    for scope, changed in by_scope.items():
        old = store.get(scope)
        tree = _collect_tree(scope, REPO_ROOT, _all_files_in_scope(scope), max_lines=200)
        # In force-full / scope modes, treat all files in scope as changed
        if args.force_full or args.scope:
            changed_files = _all_files_in_scope(scope)
        else:
            changed_files = sorted(changed)
        try:
            regen_one_scope(
                scope=scope, old_graph=old, changed_files=changed_files,
                file_tree=tree, head_sha=args.new_head or "HEAD",
                provider=provider, store=store, maps_dir=maps_dir,
            )
        except LLMAuthError as exc:
            # Mid-loop credential failure: don't burn timeouts on the rest
            log.warning("LLM auth failed mid-loop: %s", exc)
            _write_fallback_index(
                maps_dir, list(by_scope), "LLM 未配置", args.new_head or "HEAD",
            )
            return 0

    return 0  # never block pull


def _all_files_in_scope(scope: str) -> list[str]:
    out: list[str] = []
    base = REPO_ROOT / scope
    if not base.exists():
        return out
    for p in base.rglob("*"):
        if p.is_file():
            out.append(str(p.relative_to(REPO_ROOT)))
    return out


def _load_disk_into_store(maps_dir: Path, store: CodeMapStore) -> None:
    for p in maps_dir.glob("*.json"):
        if p.name == "index.json":
            continue
        scope = p.stem
        try:
            g = ScopeGraph.model_validate_json(p.read_text(encoding="utf-8"))
            store.put(scope, g)
        except Exception as exc:
            log.warning("could not load %s: %s", p, exc)


def _write_fallback_index(maps_dir: Path, scopes: list[str], reason: str, head_sha: str) -> None:
    prior = _maybe_load_index(maps_dir)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    idx = IndexFile(
        generated_at=now,
        last_pull_at=now if prior and prior.last_pull_at else None,
        last_error=reason,
    )
    for s in scopes:
        idx.scopes[s] = {
            "version": 0, "head_sha": head_sha,
            "stale": True, "stale_reason": reason,
            "module_count": 0,
        }
    _atomic_write_json(maps_dir / "index.json", json.loads(idx.model_dump_json(exclude_none=True)))


def _maybe_load_index(maps_dir: Path) -> IndexFile | None:
    p = maps_dir / "index.json"
    if not p.exists():
        return None
    try:
        return IndexFile.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(main())
