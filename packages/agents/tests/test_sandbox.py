from pathlib import Path

import pytest
from devmanager_agents.sandbox import SandboxError, safe_path


def test_safe_path_resolves_existing_file(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1")
    p = safe_path(tmp_path, "a.py")
    assert p == (tmp_path / "a.py").resolve()


def test_safe_path_blocks_traversal(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1")
    with pytest.raises(SandboxError):
        safe_path(tmp_path, "../etc/passwd")


def test_safe_path_blocks_absolute_outside_repo(tmp_path: Path):
    with pytest.raises(SandboxError):
        safe_path(tmp_path, "/etc/passwd")


def test_safe_path_returns_None_for_missing_file(tmp_path: Path):
    assert safe_path(tmp_path, "does_not_exist.py") is None
