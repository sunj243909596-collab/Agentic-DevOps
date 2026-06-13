# apps/api-gateway/tests/code_map/test_router.py
from __future__ import annotations

import api_gateway.routers.code_map.router as cm_router
import pytest
from api_gateway.routers.code_map.schema import Module, ScopeGraph
from api_gateway.routers.code_map.store import CodeMapStore
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def store_with_data():
    """Swap the router's module-level store for one with seeded data."""
    s = CodeMapStore()
    s.put(
        "apps",
        ScopeGraph(
            scope="apps",
            version=3,
            generated_at="t",
            head_sha="abc",
            generator="t",
            modules=[
                Module(id="apps/web", path="apps/web", name="Web"),
                Module(id="apps/api", path="apps/api", name="API"),
            ],
        ),
    )
    s.put(
        "agents",
        ScopeGraph(
            scope="agents",
            version=1,
            generated_at="t",
            head_sha="abc",
            generator="t",
            modules=[Module(id="agents/mgr", path="agents/manager-agent", name="Mgr")],
        ),
    )
    cm_router.set_store(s)
    yield s
    # Reset to a fresh empty store after the test
    cm_router.set_store(CodeMapStore())


@pytest.fixture
def app_with_router():
    """A minimal FastAPI app that includes only the code_map router.

    Task 9 wires the router into the production `main.app`; this fixture
    lets Task 8 be tested in isolation.
    """
    app = FastAPI()
    app.include_router(cm_router.router)
    return app


@pytest.mark.asyncio
async def test_get_index(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map")
    assert r.status_code == 200
    data = r.json()
    assert "apps" in data["scopes"]
    assert data["scopes"]["apps"]["version"] == 3


@pytest.mark.asyncio
async def test_get_scope(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map/apps")
    assert r.status_code == 200
    assert r.json()["scope"] == "apps"
    assert len(r.json()["modules"]) == 2


@pytest.mark.asyncio
async def test_get_scope_not_found(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_module(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map/apps/module/apps%2Fweb")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_get_diff(store_with_data, app_with_router):
    # Add a second version on top of v3
    store_with_data.put(
        "apps",
        ScopeGraph(
            scope="apps",
            version=4,
            generated_at="t",
            head_sha="def",
            generator="t",
            modules=[
                Module(id="apps/web", path="apps/web", name="Web"),
                Module(id="apps/api", path="apps/api", name="API"),
                Module(id="apps/api/contracts", path="apps/api/contracts", name="Contracts"),
            ],
        ),
    )
    # v1 implementation: diff uses the disk file as the "from" snapshot
    # since the repo is not a git workspace, both sides are read from disk.
    # Seed the disk file at the same absolute path the router reads from.
    from pathlib import Path

    # router.py is at apps/api-gateway/api_gateway/routers/code_map/router.py
    # → parents[5] = project root.
    # This test file is at apps/api-gateway/tests/code_map/test_router.py
    # → parents[4] = project root.
    repo_root = Path(__file__).resolve().parents[4]
    maps_dir = repo_root / "docs" / "code-map"
    maps_dir.mkdir(parents=True, exist_ok=True)
    v3 = ScopeGraph(
        scope="apps",
        version=3,
        generated_at="t",
        head_sha="abc",
        generator="t",
        modules=[
            Module(id="apps/web", path="apps/web", name="Web"),
            Module(id="apps/api", path="apps/api", name="API"),
        ],
    )
    (maps_dir / "apps.json").write_text(v3.model_dump_json(exclude_none=True), encoding="utf-8")
    try:
        transport = ASGITransport(app=app_with_router)
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/v1/code-map/apps/diff?from=3&to=4")
        assert r.status_code == 200
        d = r.json()
        assert d["from_version"] == 3
        assert d["to_version"] == 4
        # "apps/api/contracts" is new in v4 → should be in added_modules
        assert any(m["id"] == "apps/api/contracts" for m in d["added_modules"])
    finally:
        # Clean up the on-disk side effect
        if (maps_dir / "apps.json").exists():
            (maps_dir / "apps.json").unlink()


@pytest.mark.asyncio
async def test_line_context(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map/line-context?file=apps/web/src/Settings.tsx")
    assert r.status_code == 200
    data = r.json()
    assert data["module_id"] == "apps/web"
    assert data["scope"] == "apps"


@pytest.mark.asyncio
async def test_line_context_no_match(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map/line-context?file=unknown/foo.ts")
    assert r.status_code == 200
    assert r.json()["module_id"] is None


@pytest.mark.asyncio
async def test_get_changes_empty_when_no_git(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map/changes?since=0000000000000000000000000000000000000000")
    # Not a git repo OR no commit history: should return empty list, not 500
    assert r.status_code == 200
    assert "commits" in r.json()
    assert "files" in r.json()


@pytest.mark.asyncio
async def test_post_regen_returns_run_id(store_with_data, app_with_router):
    # Plan used bare `app`; we use the existing `app_with_router` fixture.
    cm_router._jobs.clear()
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.post("/v1/code-map/regen", json={"force_full": True})
    assert r.status_code == 202
    body = r.json()
    assert "run_id" in body
    assert body["status"] in ("queued", "running")


@pytest.mark.asyncio
async def test_post_regen_empty_body_defaults_to_full(store_with_data, app_with_router):
    """Regression: when the UI sends an empty body (e.g. user clicks
    重新生成 while on the Diff/Changes tab where the scope picker is
    hidden), the endpoint used to fail the job with
    'either scope or force_full must be set'. It should now default to a
    full regen and return 202."""
    cm_router._jobs.clear()
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        # Empty body (no scope, no force_full)
        r = await c.post("/v1/code-map/regen", json={})
    assert r.status_code == 202, r.text
    body = r.json()
    assert "run_id" in body
    assert body["status"] in ("queued", "running")


@pytest.mark.asyncio
async def test_get_regen_status_returns_state(store_with_data, app_with_router):
    cm_router._jobs.clear()
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r1 = await c.post("/v1/code-map/regen", json={"scope": "apps"})
        run_id = r1.json()["run_id"]
        r2 = await c.get(f"/v1/code-map/regen/{run_id}")
    assert r2.status_code == 200
    data = r2.json()
    assert data["run_id"] == run_id
    assert data["status"] in ("queued", "running", "succeeded", "failed")


@pytest.mark.asyncio
async def test_get_regen_status_unknown_run_id_404(store_with_data, app_with_router):
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.get("/v1/code-map/regen/nonexistent-id")
    assert r.status_code == 404


# ── /repull-regen (Task 14 self-healing) ────────────────────────────────────


@pytest.mark.asyncio
async def test_post_repull_regen_returns_run_id(store_with_data, app_with_router, monkeypatch):
    """repull-regen returns 202 + run_id, and the job has pull_result=null
    initially (it'll be filled in by the worker)."""
    cm_router._jobs.clear()

    # Stub the worker so it doesn't actually shell out to git
    async def fake_post_repull_regen_handler(*a, **k):  # not used
        return None

    monkeypatch.setattr(cm_router, "_run_repull_regen_job", lambda *a, **k: None)

    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r = await c.post("/v1/code-map/repull-regen", json={"force_full": True})
    assert r.status_code == 202
    body = r.json()
    assert "run_id" in body
    assert body["status"] in ("queued", "running")


@pytest.mark.asyncio
async def test_get_repull_regen_status_includes_pull_result(store_with_data, app_with_router):
    cm_router._jobs.clear()
    async with AsyncClient(transport=ASGITransport(app=app_with_router), base_url="http://t") as c:
        r1 = await c.post("/v1/code-map/repull-regen", json={"scope": "apps"})
        run_id = r1.json()["run_id"]
        r2 = await c.get(f"/v1/code-map/regen/{run_id}")
    assert r2.status_code == 200
    data = r2.json()
    # pull_result key exists, even if value is null (worker hasn't run)
    assert "pull_result" in data
    assert "phase" in data


@pytest.mark.asyncio
async def test_repull_records_pull_error_when_pull_fails(
    store_with_data, app_with_router, monkeypatch, tmp_path
):
    """When the worker shells out to git pull and it fails, the job
    transitions to phase=done with pull_result.ok=false and status=failed."""
    import subprocess as sp

    cm_router._jobs.clear()

    # Pre-seed the job entry the way the HTTP handler would
    cm_router._jobs["test-run-id"] = cm_router._new_job("apps", False)
    cm_router._jobs["test-run-id"]["run_id"] = "test-run-id"

    def fake_run(cmd, *a, **k):
        if cmd[0] == "git" and cmd[1] == "pull":

            class R:
                returncode = 1
                stderr = "fatal: could not fetch from origin (offline)"
                stdout = ""

            return R()
        return sp.run(cmd, *a, **k)

    monkeypatch.setattr(sp, "run", fake_run)
    # Run worker synchronously in the test (don't go through background_tasks)
    import api_gateway.routers.code_map.router as cm

    cm._run_repull_regen_job("test-run-id", "apps", False)
    job = cm._jobs["test-run-id"]
    assert job["status"] == "failed"
    assert job["phase"] == "done"
    assert job["pull_result"] is not None
    assert job["pull_result"]["ok"] is False
    assert "could not fetch" in job["pull_result"]["error"]


@pytest.mark.asyncio
async def test_repull_pull_timeout_marks_failed(store_with_data, app_with_router, monkeypatch):
    """subprocess.TimeoutExpired → pull_result.error contains 'timeout'."""
    import subprocess as sp

    cm_router._jobs.clear()
    cm_router._jobs["test-timeout-id"] = cm_router._new_job(None, True)
    cm_router._jobs["test-timeout-id"]["run_id"] = "test-timeout-id"

    def fake_run(cmd, *a, **k):
        if cmd[0] == "git" and cmd[1] == "pull":
            raise sp.TimeoutExpired(cmd=cmd, timeout=60)
        return sp.run(cmd, *a, **k)

    monkeypatch.setattr(sp, "run", fake_run)
    import api_gateway.routers.code_map.router as cm

    cm._run_repull_regen_job("test-timeout-id", None, True)
    job = cm._jobs["test-timeout-id"]
    assert job["status"] == "failed"
    assert "timed out" in job["pull_result"]["error"].lower()
