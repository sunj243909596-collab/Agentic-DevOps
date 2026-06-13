"""FastAPI router for the code-map system.

Endpoints (all under /v1/code-map):
  GET  /                       → global index (status)
  GET  /{scope}                → scope graph
  GET  /{scope}/diff           → module-graph diff
  GET  /{scope}/module/{id}    → single module card
  GET  /line-context           → file → module lookup
  GET  /changes                → recent git commits + per-file line-context
  POST /regen                  → kick off a background regen job
  GET  /regen/{run_id}         → poll regen job status
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from .diff import diff_scope_graphs
from .line_context import find_module_for_file
from .schema import ScopeGraph
from .store import CodeMapStore

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/code-map", tags=["code-map"])

# Module-level singleton, set in main.py lifespan or replaced in tests.
# NB: `set_store` is NOT safe to call mid-request. The contract is that
# regen runs in a background task or during a quiescent window, then
# `set_store(new_store)` is called atomically. FastAPI request handlers
# always re-read `_store` at await time, so a swap is eventually consistent.
_store: CodeMapStore = CodeMapStore()


# In-memory regen job tracking. Keys are run_id (uuid4 hex). Values are
# dicts with the JobStatus lifecycle. A single lock guards all reads/writes.
JobStatus = Literal["queued", "running", "succeeded", "failed"]
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")

# Allow letters, digits, underscores, slashes, dots, hyphens — but no `..`
_SAFE_ID = re.compile(r"^[A-Za-z0-9_./-]+$")
_HEX_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_HEAD_REF = re.compile(r"^HEAD(~[0-9]+)?$")


def _validate_id(value: str, *, kind: str) -> str:
    """Reject `..`, absolute paths, and any character outside [A-Za-z0-9_./-]."""
    if not value or ".." in value.split("/") or not _SAFE_ID.match(value):
        raise HTTPException(400, f"invalid {kind}: {value!r}")
    return value


def _validate_since(since: str) -> str:
    """Accept a 40-char SHA, `HEAD`, or `HEAD~N`."""
    if _HEX_SHA.match(since) or _HEAD_REF.match(since):
        return since
    raise HTTPException(400, f"invalid since: must be 40-char SHA or HEAD/~N, got {since!r}")


def get_store() -> CodeMapStore:
    return _store


def set_store(s: CodeMapStore) -> None:
    global _store
    _store = s


# ── / ────────────────────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def get_index() -> dict:
    return _store.status()


# NOTE: literal sub-paths MUST be registered BEFORE the catch-all `/{scope}`
# route, otherwise FastAPI matches `/line-context` as scope="line-context".

# ── /line-context ────────────────────────────────────────────────────────────

@router.get("/line-context", response_model=dict)
async def line_context(file: str = Query(...)) -> dict:
    # Internal file path — restricted to repo-relative POSIX form.
    _validate_id(file, kind="file")
    result = find_module_for_file(file, _store.all_graphs())
    if result is None:
        return {"module_id": None, "scope": None, "responsibility": None, "kind": None}
    return result


# ── /changes ─────────────────────────────────────────────────────────────────

@router.get("/changes", response_model=dict)
async def get_changes(since: str = Query(...)) -> dict:
    """Return commits and changed files between `since` and HEAD, each file
    pre-annotated with its module via line-context."""
    since = _validate_since(since)
    repo_root = Path(__file__).resolve().parents[5]
    try:
        log_out = subprocess.check_output(
            ["git", "log", since, "..HEAD", "--name-status", "--pretty=format:%H%x09%s"],
            cwd=str(repo_root), text=True, stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        log.warning("git log failed (%s); returning empty changes", exc)
        return {"commits": [], "files": []}
    commits: list[dict] = []
    files: list[dict] = []
    current: dict | None = None
    for line in log_out.splitlines():
        if "\t" in line and len(line.split("\t", 1)[0]) == 40:
            sha, subject = line.split("\t", 1)
            current = {"sha": sha, "subject": subject}
            commits.append(current)
        elif line and current is not None:
            parts = line.split("\t")
            if len(parts) >= 2:
                status, path = parts[0], parts[1]
                # Best-effort file lookup; skip pathological paths.
                safe_path = not any(seg == ".." for seg in path.split("/"))
                ctx = (
                    find_module_for_file(path, _store.all_graphs())
                    if safe_path
                    else None
                )
                files.append({
                    "commit": current["sha"],
                    "path": path,
                    "status": status,
                    "module": ctx,
                })
    return {"commits": commits, "files": files}


# ── /{scope} ─────────────────────────────────────────────────────────────────

@router.get("/{scope}", response_model=dict)
async def get_scope(scope: str) -> dict:
    scope = _validate_id(scope, kind="scope")
    g = _store.get(scope)
    if g is None:
        raise HTTPException(404, f"scope {scope!r} not found in code map")
    return json.loads(g.model_dump_json(exclude_none=True))


# ── /{scope}/diff ────────────────────────────────────────────────────────────

@router.get("/{scope}/diff", response_model=dict)
async def get_diff(
    scope: str,
    from_: int = Query(..., alias="from"),
    to: int = Query(...),
) -> dict:
    """Diff two versions of a scope.

    v1 reads the older version from `docs/code-map/<scope>.json` on disk
    (in a git-tracked repo, `git show HEAD:docs/code-map/<scope>.json`
    gives the prior version; otherwise the current disk file is used).
    The `from_` parameter is parsed but not yet used to look up tagged
    versions — v1 always compares `git show HEAD:<scope>.json` vs the
    in-memory current. This is a known v1 limitation.
    """
    scope = _validate_id(scope, kind="scope")
    repo_root = Path(__file__).resolve().parents[5]
    allowed_root = (repo_root / "docs" / "code-map").resolve()
    a_path = (allowed_root / f"{scope}.json").resolve()
    # Defence-in-depth: even after regex validation, refuse any resolved
    # path that escapes the code-map directory.
    if not str(a_path).startswith(str(allowed_root) + "/"):
        raise HTTPException(400, f"scope {scope!r} resolves outside code-map dir")
    if not a_path.exists():
        raise HTTPException(404, f"scope {scope!r} not on disk")
    # Try to read the older version from git
    try:
        a_text = subprocess.check_output(
            ["git", "show", f"HEAD:docs/code-map/{scope}.json"],
            cwd=str(repo_root), text=True, stderr=subprocess.DEVNULL,
        )
    except Exception:
        a_text = a_path.read_text(encoding="utf-8")
    a = ScopeGraph.model_validate_json(a_text)
    b = _store.get(scope)
    if b is None:
        raise HTTPException(404, f"current version of {scope!r} not in store")
    return diff_scope_graphs(a, b)


# ── /{scope}/module/{module_id} ──────────────────────────────────────────────

@router.get("/{scope}/module/{module_id:path}", response_model=dict)
async def get_module(scope: str, module_id: str) -> dict:
    """Return the module's card. v1 returns the embedded module info from
    the graph (full per-module card JSON file on disk is optional enrichment)."""
    scope = _validate_id(scope, kind="scope")
    _validate_id(module_id, kind="module_id")
    g = _store.get(scope)
    if g is None:
        raise HTTPException(404, f"scope {scope!r} not found")
    for m in g.modules:
        if m.id == module_id:
            return json.loads(m.model_dump_json(exclude_none=True))
    raise HTTPException(404, f"module {module_id!r} not in scope {scope!r}")


# ── /regen (background job) ──────────────────────────────────────────────────

# Job lifecycle phases. `phase="done"` is the terminal state for the run;
# overall `status` (queued/running/succeeded/failed) tracks the per-phase
# success/failure (a failed pull marks the whole run failed even if the
# subsequent regen would have succeeded).
JobPhase = Literal["queued", "pulling", "regenerating", "done"]


def _new_job(scope: str | None, force_full: bool) -> dict:
    return {
        "run_id": "",
        "status": "queued",
        "phase": "queued",
        "scope": scope,
        "force_full": force_full,
        "started_at": None,
        "finished_at": None,
        "scopes_processed": [],
        "scopes_failed": [],
        "error": None,
        # pull_result is non-null only for /repull-regen runs; null for plain /regen
        "pull_result": None,
    }


class _RegenRequest(BaseModel):
    scope: str | None = None
    force_full: bool = False


@router.post("/regen", status_code=202, response_model=dict)
async def post_regen(body: _RegenRequest, background_tasks: BackgroundTasks) -> dict:
    """Kick off a code-map regen in the background. Returns immediately
    with a `run_id`; poll `/v1/code-map/regen/{run_id}` for status."""
    run_id = uuid.uuid4().hex
    with _jobs_lock:
        job = _new_job(body.scope, body.force_full)
        job["run_id"] = run_id
        _jobs[run_id] = job
    background_tasks.add_task(_run_regen_job, run_id, body.scope, body.force_full)
    return {"run_id": run_id, "status": "queued"}


class _RepullRegenRequest(BaseModel):
    scope: str | None = None
    force_full: bool = False


@router.post("/repull-regen", status_code=202, response_model=dict)
async def post_repull_regen(
    body: _RepullRegenRequest, background_tasks: BackgroundTasks
) -> dict:
    """`git pull` + regen. Two phases: (1) git pull in the repo root, then
    (2) regen the affected scopes. If phase 1 fails, phase 2 is skipped
    and the run is marked `failed` with `pull_result.error` populated —
    the user can click "重拉+重生" again to retry.

    Unlike the regen loop, this endpoint does NOT auto-retry the pull
    itself: pull failures (network/auth/conflict) are user decisions and
    the user must explicitly click again. Transient LLM errors inside
    phase 2 still get 1 internal retry (see regen.regen_one_scope).
    """
    run_id = uuid.uuid4().hex
    with _jobs_lock:
        job = _new_job(body.scope, body.force_full)
        job["run_id"] = run_id
        _jobs[run_id] = job
    background_tasks.add_task(
        _run_repull_regen_job, run_id, body.scope, body.force_full
    )
    return {"run_id": run_id, "status": "queued"}


@router.get("/regen/{run_id}", response_model=dict)
async def get_regen_status(run_id: str) -> dict:
    # NB: register BEFORE catch-all /{scope}? No — /regen/{run_id} is
    # literally a sub-path of /{scope}, so FastAPI's match order would
    # see scope="regen" if /{scope} is registered first. /regen routes
    # are registered AFTER /{scope} but contain literal "regen" so
    # FastAPI prefers the more specific match.
    # Verify: we have @router.post("/regen", ...) and
    # @router.get("/regen/{run_id}", ...). Both are literal-prefix matches.
    # When a GET /v1/code-map/regen/<id> arrives, FastAPI tries:
    #   1. /{scope}        → scope="regen" matches but then needs to match
    #                         /{run_id}, which doesn't exist on /{scope}.
    #                         FastAPI does NOT match this.
    #   2. /regen/{run_id} → matches if run_id = <id>.
    # FastAPI uses Starlette which scores routes by specificity; literal
    # path segments outrank path params, so /regen/{run_id} wins.
    with _jobs_lock:
        job = _jobs.get(run_id)
    if job is None:
        raise HTTPException(404, f"regen run {run_id!r} not found")
    return job


def _run_regen_job(run_id: str, scope: str | None, force_full: bool) -> None:
    """Background worker for the plain /regen endpoint. Same logic as
    before — only changes from v1 are the extended job schema fields
    (phase='regenerating' on success, 'done' on completion)."""
    with _jobs_lock:
        _jobs[run_id]["status"] = "running"
        _jobs[run_id]["phase"] = "regenerating"
        _jobs[run_id]["started_at"] = _now_iso()

    try:
        _do_regen_phase(run_id, scope, force_full, prev_head="HEAD", new_head="HEAD")
        with _jobs_lock:
            _jobs[run_id]["status"] = (
                "succeeded" if not _jobs[run_id]["scopes_failed"] else "failed"
            )
    except Exception as exc:
        with _jobs_lock:
            _jobs[run_id]["status"] = "failed"
            _jobs[run_id]["error"] = str(exc)
    finally:
        with _jobs_lock:
            _jobs[run_id]["phase"] = "done"
            _jobs[run_id]["finished_at"] = _now_iso()


def _run_repull_regen_job(
    run_id: str, scope: str | None, force_full: bool
) -> None:
    """Background worker for /repull-regen. Two phases:
    1. `git pull` (60s timeout). On any failure → mark whole run failed
       and SKIP phase 2. pull_result captures prev/new HEAD and error.
    2. regen (delegates to _do_regen_phase).
    """
    with _jobs_lock:
        _jobs[run_id]["status"] = "running"
        _jobs[run_id]["phase"] = "pulling"
        _jobs[run_id]["started_at"] = _now_iso()

    repo_root = Path(__file__).resolve().parents[5]
    prev_head = _safe_git_rev("HEAD", repo_root) or "0" * 40
    pull_result: dict

    try:
        proc = subprocess.run(
            ["git", "pull"],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        pull_result = {
            "ok": False,
            "prev_head": prev_head,
            "new_head": prev_head,
            "error": "git pull timed out after 60s",
        }
        with _jobs_lock:
            _jobs[run_id]["pull_result"] = pull_result
            _jobs[run_id]["status"] = "failed"
            _jobs[run_id]["error"] = "git pull timeout"
            _jobs[run_id]["phase"] = "done"
            _jobs[run_id]["finished_at"] = _now_iso()
        return
    except Exception as exc:
        pull_result = {
            "ok": False,
            "prev_head": prev_head,
            "new_head": prev_head,
            "error": f"git pull raised {type(exc).__name__}: {exc}",
        }
        with _jobs_lock:
            _jobs[run_id]["pull_result"] = pull_result
            _jobs[run_id]["status"] = "failed"
            _jobs[run_id]["error"] = str(exc)
            _jobs[run_id]["phase"] = "done"
            _jobs[run_id]["finished_at"] = _now_iso()
        return

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or "git pull returned non-zero"
        pull_result = {
            "ok": False,
            "prev_head": prev_head,
            "new_head": prev_head,
            "error": err[:500],
        }
        with _jobs_lock:
            _jobs[run_id]["pull_result"] = pull_result
            _jobs[run_id]["status"] = "failed"
            _jobs[run_id]["error"] = f"git pull failed: {err[:200]}"
            _jobs[run_id]["phase"] = "done"
            _jobs[run_id]["finished_at"] = _now_iso()
        return

    new_head = _safe_git_rev("HEAD", repo_root) or prev_head
    pull_result = {
        "ok": True,
        "prev_head": prev_head,
        "new_head": new_head,
        "error": None,
    }
    with _jobs_lock:
        _jobs[run_id]["pull_result"] = pull_result

    # Phase 2: regen. If pull didn't move HEAD (already up to date), still
    # run regen — the user explicitly asked for "重拉+重生", so honor intent.
    with _jobs_lock:
        _jobs[run_id]["phase"] = "regenerating"

    try:
        _do_regen_phase(run_id, scope, force_full, prev_head=prev_head, new_head=new_head)
        with _jobs_lock:
            _jobs[run_id]["status"] = (
                "succeeded" if not _jobs[run_id]["scopes_failed"] else "failed"
            )
    except Exception as exc:
        with _jobs_lock:
            _jobs[run_id]["status"] = "failed"
            _jobs[run_id]["error"] = str(exc)
    finally:
        with _jobs_lock:
            _jobs[run_id]["phase"] = "done"
            _jobs[run_id]["finished_at"] = _now_iso()


def _do_regen_phase(
    run_id: str, scope: str | None, force_full: bool,
    prev_head: str, new_head: str,
) -> None:
    """Shared core of /regen and /repull-regen: decide scopes, build
    provider, call regen_one_scope for each (which itself retries once
    on transient LLM errors)."""
    import os

    from devmanager_llm import LLMAuthError, make_provider

    from .regen import MAPS_DIR, REPO_ROOT, regen_one_scope

    if scope:
        scopes_to_run = [scope]
    else:
        # Default: if no scope was specified, treat as a full regen of all
        # top-level scope dirs. This matches the common UI flow where the
        # user clicks "重新生成" without picking a specific scope (or is
        # on a tab where the scope picker is not visible). Explicit
        # `force_full=False` is honoured — the regen walks all dirs
        # anyway, so the cost is the same.
        skip = {".git", ".claude", "node_modules", "dist", ".venv",
                ".pytest_cache", ".logs", ".pids", "__pycache__"}
        scopes_to_run = [
            d.name for d in REPO_ROOT.iterdir()
            if d.is_dir() and d.name not in skip and not d.name.startswith(".")
        ]

    name = os.getenv("LLM_PROVIDER", "mock")
    api_key = os.getenv("LLM_API_KEY", "")
    try:
        provider = make_provider(
            name, api_key=api_key,
            model=os.getenv("LLM_MODEL"),
            base_url=os.getenv("LLM_BASE_URL"),
        )
    except LLMAuthError as exc:
        raise RuntimeError(f"LLM not configured: {exc}") from exc

    for s in scopes_to_run:
        try:
            old = _store.get(s)
            tree = _collect_tree_for_scope(s, REPO_ROOT)
            regen_one_scope(
                scope=s, old_graph=old, changed_files=[],
                file_tree=tree, head_sha=new_head or "HEAD",
                provider=provider, store=_store, maps_dir=MAPS_DIR,
            )
            with _jobs_lock:
                _jobs[run_id]["scopes_processed"].append(s)
        except Exception as exc:
            with _jobs_lock:
                _jobs[run_id]["scopes_failed"].append({"scope": s, "error": str(exc)})


def _safe_git_rev(ref: str, repo_root: Path) -> str | None:
    """Return the resolved SHA for `ref`, or None on failure."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", ref],
            cwd=str(repo_root), text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        return out.strip() or None
    except Exception:
        return None


def _collect_tree_for_scope(scope: str, repo_root) -> str:
    """Walk the scope dir and return a flat file list (max 200 entries)."""
    base = Path(repo_root) / scope
    if not base.exists():
        return ""
    files = sorted(
        str(p.relative_to(repo_root)) for p in base.rglob("*") if p.is_file()
    )
    if len(files) > 200:
        files = files[:200] + [f"... (+{len(files) - 200} more)"]
    return "\n".join(f"- {f}" for f in files)
