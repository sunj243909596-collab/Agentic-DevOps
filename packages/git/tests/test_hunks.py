from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest
from devmanager_git.fetcher import _EMPTY_TREE
from devmanager_git.hunks import extract_all_hunks, extract_hunk


@pytest.fixture
def git_repo(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=work, capture_output=True, check=True)

    git("init")
    git("config", "user.email", "t@t.com")
    git("config", "user.name", "T")
    (work / "hello.py").write_text("print('hello')\n")
    git("add", "hello.py")
    git("commit", "-m", "init")
    sha1 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True
    ).stdout.strip()

    (work / "hello.py").write_text("print('hello world')\n")
    git("add", "hello.py")
    git("commit", "-m", "update")
    sha2 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True
    ).stdout.strip()

    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "clone", "--mirror", str(work), str(bare)], capture_output=True, check=True
    )
    return {"bare": bare, "sha1": sha1, "sha2": sha2}


@pytest.mark.asyncio
async def test_extract_hunk_writes_file(tmp_path: Path, git_repo: dict):
    out = tmp_path / "patch.diff"
    ref = await extract_hunk(git_repo["bare"], git_repo["sha1"], git_repo["sha2"], "hello.py", out)
    assert ref is not None
    assert ref.startswith("file://")
    assert out.exists()
    content = out.read_text()
    assert "hello" in content
    assert "@@" in content


@pytest.mark.asyncio
async def test_extract_hunk_nonexistent_file_returns_none(tmp_path: Path, git_repo: dict):
    out = tmp_path / "nope.diff"
    ref = await extract_hunk(
        git_repo["bare"], git_repo["sha1"], git_repo["sha2"], "no_such_file.py", out
    )
    assert ref is None


@pytest.mark.asyncio
async def test_extract_all_hunks(tmp_path: Path, git_repo: dict):
    cu_id = uuid.uuid4()
    units = [
        {
            "change_unit_id": cu_id,
            "file_path": "hello.py",
            "is_binary": False,
            "is_generated": False,
            "is_vendor": False,
        }
    ]
    hunks_dir = tmp_path / "hunks"
    result = await extract_all_hunks(
        repo_dir=git_repo["bare"],
        from_ref=git_repo["sha1"],
        to_ref=git_repo["sha2"],
        units=units,
        hunks_dir=hunks_dir,
    )
    assert str(cu_id) in result
    assert result[str(cu_id)].startswith("file://")


@pytest.mark.asyncio
async def test_extract_all_hunks_skips_binary(tmp_path: Path, git_repo: dict):
    cu_id = uuid.uuid4()
    units = [
        {
            "change_unit_id": cu_id,
            "file_path": "image.png",
            "is_binary": True,
            "is_generated": False,
            "is_vendor": False,
        }
    ]
    result = await extract_all_hunks(
        repo_dir=git_repo["bare"],
        from_ref=git_repo["sha1"],
        to_ref=git_repo["sha2"],
        units=units,
        hunks_dir=tmp_path / "hunks",
    )
    assert str(cu_id) not in result


@pytest.mark.asyncio
async def test_extract_hunk_from_empty_tree(tmp_path: Path, git_repo: dict):
    out = tmp_path / "from_empty.diff"
    ref = await extract_hunk(git_repo["bare"], _EMPTY_TREE, git_repo["sha1"], "hello.py", out)
    assert ref is not None
    assert out.exists()
    assert "hello" in out.read_text()
