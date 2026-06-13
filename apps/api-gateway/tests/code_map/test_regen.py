# apps/api-gateway/tests/code_map/test_regen.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from api_gateway.routers.code_map import regen
from api_gateway.routers.code_map.schema import ScopeGraph


def test_get_changed_files_in_a_git_repo(tmp_path):
    # Create a tiny git repo with one commit
    subprocess.check_call(["git", "init", "-q"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.email", "t@t"], cwd=tmp_path)
    subprocess.check_call(["git", "config", "user.name", "t"], cwd=tmp_path)
    (tmp_path / "a.txt").write_text("a")
    subprocess.check_call(["git", "add", "."], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-q", "-m", "init"], cwd=tmp_path)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path).decode().strip()
    (tmp_path / "b.txt").write_text("b")
    subprocess.check_call(["git", "add", "."], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-q", "-m", "add b"], cwd=tmp_path)
    files = regen._get_changed_files(str(tmp_path), head, "HEAD")
    assert "b.txt" in files


def test_group_changed_files_by_scope():
    files = ["apps/web/foo.ts", "apps/api/bar.py", "agents/x.py", "docs/readme.md", "unrelated.txt"]
    out = regen._group_by_scope(files)
    # Each file is grouped under its top-level directory (or the full filename if no "/")
    assert out == {
        "apps": {"apps/web/foo.ts", "apps/api/bar.py"},
        "agents": {"agents/x.py"},
        "docs": {"docs/readme.md"},
        "unrelated.txt": {"unrelated.txt"},
    }


def test_collect_tree_caps_at_max():
    files = [f"apps/web/f{i}.ts" for i in range(500)]
    tree = regen._collect_tree("apps", Path("/nonexistent"), files, max_lines=100)
    lines = tree.splitlines()
    assert len(lines) <= 102  # 100 + header room


def test_regen_one_scope_writes_files(tmp_path, monkeypatch):
    # Mock LLM to return a valid graph
    from devmanager_llm import LLMResponse

    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "scope": "apps",
                    "version": 1,
                    "generated_at": "2026-06-09T12:00:00Z",
                    "head_sha": "x",
                    "generator": "mock",
                    "modules": [
                        {
                            "id": "apps/web",
                            "path": "apps/web",
                            "name": "Web",
                            "kind": "frontend-spa",
                            "responsibility": "Vue SPA",
                            "entry_points": [],
                            "key_files": [],
                        }
                    ],
                    "edges": [],
                }
            ),
            model="mock",
        )
    )

    # Set up: write v0 index, mock store
    code_map_dir = tmp_path / "code-map"
    code_map_dir.mkdir()
    (code_map_dir / "index.json").write_text(
        json.dumps({"generated_at": "t", "last_pull_at": None, "last_error": None, "scopes": {}})
    )

    store = MagicMock()
    monkeypatch.setattr(regen, "MAPS_DIR", code_map_dir)

    regen.regen_one_scope(
        scope="apps",
        old_graph=None,
        changed_files=[],
        file_tree="- apps/web/src/main.tsx",
        head_sha="abc",
        provider=mock_provider,
        store=store,
    )

    assert (code_map_dir / "apps.json").exists()
    assert (code_map_dir / "apps" / "web.json").exists()
    store.put.assert_called_once()
    args, kwargs = store.put.call_args
    assert args[0] == "apps"
    assert isinstance(args[1], ScopeGraph)


def test_regen_one_scope_handles_llm_failure(tmp_path, monkeypatch):
    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.complete = AsyncMock(side_effect=RuntimeError("LLM timeout"))
    store = MagicMock()
    code_map_dir = tmp_path / "code-map"
    code_map_dir.mkdir()
    monkeypatch.setattr(regen, "MAPS_DIR", code_map_dir)

    regen.regen_one_scope(
        scope="apps",
        old_graph=None,
        changed_files=[],
        file_tree="- x.ts",
        head_sha="abc",
        provider=mock_provider,
        store=store,
    )

    # store.put was called with stale=True
    store.put.assert_called_once()
    kwargs = store.put.call_args.kwargs
    assert kwargs["stale"] is True
    assert "timeout" in kwargs["stale_reason"].lower()


def test_main_with_force_full_ignores_changed_files(tmp_path, monkeypatch):
    """force-full should not require --prev-head/--new-head and should
    treat *all* top-level dirs as affected."""
    from devmanager_llm import LLMResponse

    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "scope": "agents",
                    "version": 1,
                    "generated_at": "t",
                    "head_sha": "x",
                    "generator": "mock",
                    "modules": [],
                    "edges": [],
                }
            ),
            model="mock",
        )
    )

    monkeypatch.setattr(regen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(regen, "MAPS_DIR", tmp_path / "docs" / "code-map")
    monkeypatch.setattr(regen, "_load_disk_into_store", lambda *a, **k: None)

    # `main()` does `from devmanager_llm import make_provider` at runtime,
    # so patch at the source so the runtime import picks up our mock.
    import devmanager_llm

    monkeypatch.setattr(devmanager_llm, "make_provider", lambda *a, **k: mock_provider)

    # Make two top-level dirs
    (tmp_path / "apps").mkdir()
    (tmp_path / "agents").mkdir()

    rc = regen.main(["--force-full"])
    assert rc == 0
    # Both apps and agents should be regenerated (or attempted)
    assert mock_provider.complete.call_count >= 2


def test_main_with_scope_only_regens_that_one(tmp_path, monkeypatch):
    from devmanager_llm import LLMResponse

    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "scope": "apps",
                    "version": 1,
                    "generated_at": "t",
                    "head_sha": "x",
                    "generator": "mock",
                    "modules": [],
                    "edges": [],
                }
            ),
            model="mock",
        )
    )

    monkeypatch.setattr(regen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(regen, "MAPS_DIR", tmp_path / "docs" / "code-map")
    monkeypatch.setattr(regen, "_load_disk_into_store", lambda *a, **k: None)

    import devmanager_llm

    monkeypatch.setattr(devmanager_llm, "make_provider", lambda *a, **k: mock_provider)

    (tmp_path / "apps").mkdir()
    (tmp_path / "agents").mkdir()  # exists but should NOT be touched

    rc = regen.main(["--scope", "apps", "--force-full"])
    assert rc == 0
    # Verify only "apps" was sent to the LLM. regen_one_scope calls
    # provider.complete(messages=..., ...) with keyword args, so the
    # messages list lives in c.kwargs, not c.args.
    called_scopes = [
        (c.kwargs.get("messages") or c.args[0])[0].content.split("scope = ")[1].split("\n")[0]
        for c in mock_provider.complete.call_args_list
    ]
    assert all(s == "apps" for s in called_scopes)


# ── error classification + transient retry (Task 14 / self-healing) ──────────


def test_classify_error_marks_llm_auth_as_permanent():
    from devmanager_llm import LLMAuthError

    assert regen.classify_error(LLMAuthError("no key")) == "permanent"


def test_classify_error_marks_timeout_as_transient():
    assert regen.classify_error(TimeoutError("upstream slow")) == "transient"


def test_classify_error_marks_connection_reset_as_transient():
    assert regen.classify_error(ConnectionError("reset by peer")) == "transient"


def test_classify_error_marks_5xx_string_as_transient():
    assert regen.classify_error(RuntimeError("upstream 503 service unavailable")) == "transient"


def test_classify_error_marks_schema_error_as_permanent():
    # A bare ValueError (the kind pydantic raises on bad types) → permanent
    assert regen.classify_error(ValueError("schema mismatch")) == "permanent"


def test_regen_one_scope_retries_on_transient_error(tmp_path, monkeypatch):
    """First call raises transient, second succeeds. Sleep is a no-op."""
    from devmanager_llm import LLMResponse

    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.complete = AsyncMock(
        side_effect=[
            TimeoutError("upstream 504 gateway timeout"),
            LLMResponse(
                content=json.dumps(
                    {
                        "scope": "apps",
                        "version": 1,
                        "generated_at": "t",
                        "head_sha": "x",
                        "generator": "mock",
                        "modules": [],
                        "edges": [],
                    }
                ),
                model="mock",
            ),
        ]
    )
    store = MagicMock()
    code_map_dir = tmp_path / "code-map"
    code_map_dir.mkdir()
    monkeypatch.setattr(regen, "MAPS_DIR", code_map_dir)

    regen.regen_one_scope(
        scope="apps",
        old_graph=None,
        changed_files=[],
        file_tree="- x.ts",
        head_sha="abc",
        provider=mock_provider,
        store=store,
        sleep=lambda _s: None,
    )
    # Two LLM calls: one failed transiently, one succeeded
    assert mock_provider.complete.call_count == 2
    # Final state: store.put called once with the success graph (no stale kwarg)
    store.put.assert_called_once()
    assert "stale" not in store.put.call_args.kwargs


def test_regen_one_scope_does_not_retry_permanent_error(tmp_path, monkeypatch):
    """Permanent error: only 1 LLM call, store gets stale fallback."""
    from devmanager_llm import LLMAuthError

    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.complete = AsyncMock(side_effect=LLMAuthError("no api key"))
    store = MagicMock()
    code_map_dir = tmp_path / "code-map"
    code_map_dir.mkdir()
    monkeypatch.setattr(regen, "MAPS_DIR", code_map_dir)

    regen.regen_one_scope(
        scope="apps",
        old_graph=None,
        changed_files=[],
        file_tree="- x.ts",
        head_sha="abc",
        provider=mock_provider,
        store=store,
        sleep=lambda _s: None,
    )
    assert mock_provider.complete.call_count == 1  # no retry
    store.put.assert_called_once()
    kwargs = store.put.call_args.kwargs
    assert kwargs["stale"] is True
    assert "no api key" in kwargs["stale_reason"]


def test_regen_one_scope_gives_up_after_max_attempts(tmp_path, monkeypatch):
    """All attempts transient, finally mark stale."""
    mock_provider = MagicMock()
    mock_provider.name = "mock"
    mock_provider.complete = AsyncMock(side_effect=TimeoutError("nope"))
    store = MagicMock()
    code_map_dir = tmp_path / "code-map"
    code_map_dir.mkdir()
    monkeypatch.setattr(regen, "MAPS_DIR", code_map_dir)

    regen.regen_one_scope(
        scope="apps",
        old_graph=None,
        changed_files=[],
        file_tree="- x.ts",
        head_sha="abc",
        provider=mock_provider,
        store=store,
        max_attempts=2,
        sleep=lambda _s: None,
    )
    assert mock_provider.complete.call_count == 2  # 1 initial + 1 retry
    store.put.assert_called_once()
    kwargs = store.put.call_args.kwargs
    assert kwargs["stale"] is True
    assert "nope" in kwargs["stale_reason"]
