from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from devmanager_git.fetcher import (
    _EMPTY_TREE,
    _NULL_SHA,
    clone_or_fetch,
    detect_history_rewrite,
    get_diff_name_status,
    get_diff_numstat,
    resolve_merge_base,
)


@pytest.fixture
def git_repo(tmp_path: Path):
    """Create a local bare+working git repo pair for testing."""
    work = tmp_path / "work"
    work.mkdir()

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=work, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.email", "test@test.com")
    git("config", "user.name", "Test")

    # Initial commit
    (work / "README.md").write_text("# Hello\n")
    git("add", "README.md")
    git("commit", "-m", "init")
    sha1 = git("rev-parse", "HEAD")

    # Second commit
    (work / "src").mkdir()
    (work / "src" / "main.py").write_text("print('hello')\n")
    git("add", "src/main.py")
    git("commit", "-m", "add main")
    sha2 = git("rev-parse", "HEAD")

    # Create bare clone for mirror operations
    bare = tmp_path / "bare.git"
    subprocess.run(
        ["git", "clone", "--mirror", str(work), str(bare)], capture_output=True, check=True
    )

    return {"work": work, "bare": bare, "sha1": sha1, "sha2": sha2}


@pytest.mark.asyncio
async def test_clone_or_fetch_creates_bare_clone(tmp_path: Path, git_repo: dict):
    target = tmp_path / "cloned.git"
    await clone_or_fetch(str(git_repo["work"]), target)
    assert (target / "HEAD").exists()


@pytest.mark.asyncio
async def test_clone_or_fetch_refetch(tmp_path: Path, git_repo: dict):
    target = tmp_path / "cloned.git"
    await clone_or_fetch(str(git_repo["work"]), target)
    # Second call should fetch without error
    await clone_or_fetch(str(git_repo["work"]), target)
    assert (target / "HEAD").exists()


@pytest.mark.asyncio
async def test_resolve_merge_base_same_branch(git_repo: dict):
    bare = git_repo["bare"]
    sha1 = git_repo["sha1"]
    sha2 = git_repo["sha2"]
    mb = await resolve_merge_base(bare, sha1, sha2)
    # sha1 is ancestor of sha2, so merge-base = sha1
    assert mb == sha1


@pytest.mark.asyncio
async def test_resolve_merge_base_null_sha(git_repo: dict):
    bare = git_repo["bare"]
    sha2 = git_repo["sha2"]
    mb = await resolve_merge_base(bare, _NULL_SHA, sha2)
    assert mb == _EMPTY_TREE


@pytest.mark.asyncio
async def test_detect_history_rewrite_false(git_repo: dict):
    bare = git_repo["bare"]
    sha1, sha2 = git_repo["sha1"], git_repo["sha2"]
    rewritten = await detect_history_rewrite(bare, sha1, sha2)
    assert rewritten is False


@pytest.mark.asyncio
async def test_detect_history_rewrite_null_baseline(git_repo: dict):
    bare = git_repo["bare"]
    sha2 = git_repo["sha2"]
    rewritten = await detect_history_rewrite(bare, _NULL_SHA, sha2)
    assert rewritten is False


@pytest.mark.asyncio
async def test_get_diff_numstat(git_repo: dict):
    bare = git_repo["bare"]
    sha1, sha2 = git_repo["sha1"], git_repo["sha2"]
    out = await get_diff_numstat(bare, sha1, sha2)
    assert "src/main.py" in out


@pytest.mark.asyncio
async def test_get_diff_name_status(git_repo: dict):
    bare = git_repo["bare"]
    sha1, sha2 = git_repo["sha1"], git_repo["sha2"]
    out = await get_diff_name_status(bare, sha1, sha2)
    assert "A" in out
    assert "main.py" in out


@pytest.mark.asyncio
async def test_get_diff_from_empty_tree(git_repo: dict):
    bare = git_repo["bare"]
    sha2 = git_repo["sha2"]
    numstat = await get_diff_numstat(bare, _EMPTY_TREE, sha2)
    name_status = await get_diff_name_status(bare, _EMPTY_TREE, sha2)
    assert "README.md" in numstat or "main.py" in numstat
    assert "A" in name_status
