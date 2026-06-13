"""End-to-end integration test for the code-map regen pipeline.

Simulates the full post-pull flow:
  git pull → regen.main() → writes docs/code-map/<scope>.json + index.json
  → on-disk artifacts readable by the API router.

The LLM is mocked. A real `git` binary is required (used by regen.main
and by the test itself to construct a tiny repo history).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from devmanager_llm import LLMResponse


def _git(*args: str, cwd: Path) -> str:
    """Run a git command in `cwd` and return stdout (stripped)."""
    out = subprocess.check_output(["git", *args], cwd=str(cwd), text=True)
    return out.strip()


def _setup_temp_git_repo(tmp: Path) -> Path:
    """Initialize a tiny repo that resembles our real layout.

    Creates apps/web/main.tsx and an empty docs/code-map/index.json,
    then commits everything as the initial state.
    """
    _git("init", "-q", cwd=tmp)
    _git("config", "user.email", "t@t", cwd=tmp)
    _git("config", "user.name", "t", cwd=tmp)

    (tmp / "apps" / "web").mkdir(parents=True)
    (tmp / "apps" / "web" / "main.tsx").write_text("// entry", encoding="utf-8")
    (tmp / "docs" / "code-map").mkdir(parents=True)
    (tmp / "docs" / "code-map" / "index.json").write_text(
        json.dumps(
            {
                "generated_at": "t",
                "last_pull_at": None,
                "last_error": None,
                "scopes": {},
            }
        ),
        encoding="utf-8",
    )
    _git("add", ".", cwd=tmp)
    _git("commit", "-q", "-m", "init", cwd=tmp)
    return tmp


def _make_mock_provider(payload: dict) -> MagicMock:
    """Build a MagicMock that quacks like an LLMProvider."""
    p = MagicMock()
    p.name = "mock"
    p.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(payload),
            model="mock",
        )
    )
    return p


def test_e2e_pull_then_regen_writes_scope_and_index(tmp_path, monkeypatch):
    """End-to-end: a pull that changes a file triggers regen, which writes
    both the scope graph (`apps.json`) and the per-module card
    (`apps/web.json`), and updates the index. The mock LLM response omits
    `stale` / `stale_reason` because the regen pipeline always overrides
    them after parsing."""
    _setup_temp_git_repo(tmp_path)

    # Make a second commit so there's a prev/new HEAD delta to analyze.
    (tmp_path / "apps" / "web" / "Settings.tsx").write_text("// new", encoding="utf-8")
    _git("add", ".", cwd=tmp_path)
    _git("commit", "-q", "-m", "add Settings", cwd=tmp_path)
    new_head = _git("rev-parse", "HEAD", cwd=tmp_path)
    prev_head = _git("rev-parse", "HEAD~1", cwd=tmp_path)

    # The mock graph the LLM will return. Note: it omits "stale" / "stale_reason"
    # because the regen pipeline always overrides those after parsing.
    payload = {
        "scope": "apps",
        "version": 1,
        "generated_at": "t",
        "head_sha": "x",
        "generator": "mock",
        "modules": [
            {
                "id": "apps/web",
                "path": "apps/web",
                "name": "Web",
                "kind": "frontend-spa",
                "responsibility": "Vue SPA",
                "entry_points": ["apps/web/main.tsx"],
                "key_files": [],
            }
        ],
        "edges": [],
    }
    mock_provider = _make_mock_provider(payload)

    # Redirect the regen module at the temp repo so it doesn't touch the
    # real working tree. Also skip the disk→store load (we don't seed it).
    from api_gateway.routers.code_map import regen

    monkeypatch.setattr(regen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(regen, "MAPS_DIR", tmp_path / "docs" / "code-map")
    monkeypatch.setattr(regen, "_load_disk_into_store", lambda *a, **k: None)

    # `main()` does `from devmanager_llm import make_provider` at runtime,
    # so patch at the source so the runtime import picks up our mock.
    import devmanager_llm

    monkeypatch.setattr(devmanager_llm, "make_provider", lambda *a, **k: mock_provider)

    # Run
    rc = regen.main(["--prev-head", prev_head, "--new-head", new_head])
    assert rc == 0, "regen.main should exit 0 even on partial success"

    # Verify scope graph was written to disk
    apps_json = (tmp_path / "docs" / "code-map" / "apps.json").read_text(encoding="utf-8")
    g = json.loads(apps_json)
    assert g["scope"] == "apps"
    assert g["version"] == 1
    assert len(g["modules"]) == 1
    assert g["modules"][0]["id"] == "apps/web"

    # Verify the per-module card was written
    assert (tmp_path / "docs" / "code-map" / "apps" / "web.json").exists()

    # Verify the index was updated
    idx = json.loads((tmp_path / "docs" / "code-map" / "index.json").read_text(encoding="utf-8"))
    assert "apps" in idx["scopes"]
    assert idx["scopes"]["apps"]["version"] == 1
    assert idx["scopes"]["apps"]["module_count"] == 1
    # The regen pipeline always sets last_pull_at after a successful write
    assert idx["last_pull_at"] is not None


def test_e2e_regen_skips_when_no_files_changed(tmp_path, monkeypatch):
    """If the prev/new HEADs are identical, no scopes are affected and the
    CLI must return 0 without invoking the LLM."""
    _setup_temp_git_repo(tmp_path)
    head = _git("rev-parse", "HEAD", cwd=tmp_path)

    mock_provider = _make_mock_provider({})

    from api_gateway.routers.code_map import regen

    monkeypatch.setattr(regen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(regen, "MAPS_DIR", tmp_path / "docs" / "code-map")

    import devmanager_llm

    called = MagicMock(side_effect=lambda *a, **k: mock_provider)
    monkeypatch.setattr(devmanager_llm, "make_provider", called)

    rc = regen.main(["--prev-head", head, "--new-head", head])
    assert rc == 0
    # No scope files should have been created
    assert not (tmp_path / "docs" / "code-map" / "apps.json").exists()
    # Provider factory should NOT have been called — we short-circuit before
    # it is even imported.
    called.assert_not_called()


def test_e2e_falls_back_to_index_on_llm_auth_error(tmp_path, monkeypatch):
    """If `make_provider` raises LLMAuthError, regen must write a fallback
    index (so the UI can show a banner) and return 0 — never block the
    developer's git pull."""
    _setup_temp_git_repo(tmp_path)
    (tmp_path / "apps" / "web" / "Settings.tsx").write_text("// new", encoding="utf-8")
    _git("add", ".", cwd=tmp_path)
    _git("commit", "-q", "-m", "add Settings", cwd=tmp_path)
    new_head = _git("rev-parse", "HEAD", cwd=tmp_path)
    prev_head = _git("rev-parse", "HEAD~1", cwd=tmp_path)

    from api_gateway.routers.code_map import regen
    from devmanager_llm import LLMAuthError

    monkeypatch.setattr(regen, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(regen, "MAPS_DIR", tmp_path / "docs" / "code-map")

    import devmanager_llm

    def _boom(*a, **k):
        raise LLMAuthError("no api key")

    monkeypatch.setattr(devmanager_llm, "make_provider", _boom)

    rc = regen.main(["--prev-head", prev_head, "--new-head", new_head])
    assert rc == 0

    # Fallback index must exist with the error recorded
    idx_path = tmp_path / "docs" / "code-map" / "index.json"
    assert idx_path.exists()
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    assert idx["last_error"] is not None
    assert "apps" in idx["scopes"]
    assert idx["scopes"]["apps"]["stale"] is True
