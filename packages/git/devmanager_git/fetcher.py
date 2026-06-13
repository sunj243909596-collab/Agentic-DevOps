from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_NULL_SHA = "0" * 40


class GitError(Exception):
    pass


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        # DO NOT use text=True here: git's smart HTTP protocol needs to write
        # the request body (want/have negotiation) on stdin. With text=True,
        # Python closes stdin, git fails to send the body, and GitLab returns
        # 403 "unable to update url base from redirection".
        text=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else ""
        raise GitError(f"{' '.join(args)} failed: {stderr}")
    return result.stdout.decode("utf-8", errors="replace")


async def run_git(args: list[str], cwd: Path) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run, args, cwd)


def _inject_token(url: str, token: str | None) -> str:
    if not token or not url.startswith("https://"):
        return url
    return url.replace("https://", f"https://oauth2:{token}@", 1)


async def clone_or_fetch(clone_url: str, repo_dir: Path, access_token: str | None = None) -> None:
    effective_url = _inject_token(clone_url, access_token)
    if (repo_dir / "HEAD").exists():
        await run_git(["git", "remote", "set-url", "origin", effective_url], repo_dir)
        await run_git(["git", "fetch", "--prune", "origin"], repo_dir)
    else:
        repo_dir.mkdir(parents=True, exist_ok=True)
        await run_git(["git", "clone", "--mirror", effective_url, str(repo_dir)], repo_dir.parent)


async def resolve_sha(repo_dir: Path, ref: str) -> str:
    out = await run_git(["git", "rev-parse", "--verify", ref], repo_dir)
    return out.strip()


async def resolve_merge_base(repo_dir: Path, baseline_sha: str, target_sha: str) -> str:
    if baseline_sha == _NULL_SHA:
        return _EMPTY_TREE
    try:
        out = await run_git(["git", "merge-base", baseline_sha, target_sha], repo_dir)
        return out.strip()
    except GitError:
        return _EMPTY_TREE


async def detect_history_rewrite(repo_dir: Path, baseline_sha: str, target_sha: str) -> bool:
    if baseline_sha == _NULL_SHA:
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline_sha, target_sha],
        cwd=repo_dir,
        capture_output=True,
    )
    return result.returncode != 0


async def get_diff_numstat(repo_dir: Path, from_ref: str, to_ref: str) -> str:
    if from_ref == _EMPTY_TREE:
        return await run_git(["git", "diff", "--numstat", _EMPTY_TREE, to_ref], repo_dir)
    return await run_git(["git", "diff", "--numstat", from_ref, to_ref], repo_dir)


async def get_diff_name_status(repo_dir: Path, from_ref: str, to_ref: str) -> str:
    if from_ref == _EMPTY_TREE:
        return await run_git(["git", "diff", "--name-status", "-M", _EMPTY_TREE, to_ref], repo_dir)
    return await run_git(["git", "diff", "--name-status", "-M", from_ref, to_ref], repo_dir)


# ── Read-only file browser ────────────────────────────────────────────────────


async def list_refs(repo_dir: Path) -> list[dict]:
    """Return all branches + tags as [{name, type, sha}]."""
    out = await run_git(
        [
            "git",
            "for-each-ref",
            "--format=%(objectname)|%(refname:short)|%(refname)",
            "--sort=-committerdate",
        ],
        repo_dir,
    )
    refs: list[dict] = []
    for line in out.strip().splitlines():
        if not line:
            continue
        sha, short, full = line.split("|", 2)
        if full.startswith("refs/heads/"):
            ref_type = "branch"
        elif full.startswith("refs/tags/"):
            ref_type = "tag"
        else:
            ref_type = "other"
        refs.append({"name": short, "type": ref_type, "sha": sha})
    return refs


async def resolve_path(repo_dir: Path, ref: str, path: str) -> str | None:
    """Return the SHA of a file/dir at ref+path, or None if not found."""
    target = path.strip("/")
    if not target:
        return await resolve_sha(repo_dir, ref)
    try:
        out = await run_git(["git", "rev-parse", f"{ref}:{target}"], repo_dir)
        return out.strip()
    except GitError:
        return None


async def list_tree(repo_dir: Path, ref: str, path: str = "") -> list[dict]:
    """List files and directories at ref+path. Returns [{name, path, type, size}]."""
    target = path.strip("/") or "."
    if target == ".":
        args = ["git", "ls-tree", "-l", ref]
    else:
        # Trailing slash forces git to treat the path as a directory listing
        # (without it, an empty tree returns nothing).
        args = ["git", "ls-tree", "-l", f"{ref}:{target}/"]
    out = await run_git(args, repo_dir)
    items: list[dict] = []
    for line in out.strip().splitlines():
        if not line:
            continue
        # format: <mode> <type> <object>\t<name>
        # `-l` adds size: <mode> <type> <object> <size>\t<name>
        head, name = line.split("\t", 1)
        parts = head.split()
        if len(parts) == 4:
            _mode, kind, _sha, size = parts
        else:
            _mode, kind, _sha = parts
            size = None
        full_path = f"{target}/{name}" if target != "." else name
        items.append(
            {
                "name": name,
                "path": full_path,
                "type": kind,  # 'blob' (file) or 'tree' (dir)
                "size": int(size) if size and size != "-" else None,
            }
        )
    items.sort(key=lambda x: (0 if x["type"] == "tree" else 1, x["name"].lower()))
    return items


async def read_file(repo_dir: Path, ref: str, path: str) -> dict:
    """Return file content + metadata. Supports '..' containment check."""
    target = path.strip("/")
    if not target or ".." in target.split("/"):
        raise GitError("invalid path")
    out = await run_git(["git", "cat-file", "blob", f"{ref}:{target}"], repo_dir)
    try:
        text = out
        is_text = True
        # Heuristic: if it decodes as utf-8 cleanly, treat as text
        try:
            text.encode("utf-8").decode("utf-8")
        except UnicodeError:
            is_text = False
        return {
            "content": text if is_text else None,
            "is_text": is_text,
            "size": len(out),
            "encoding": "utf-8" if is_text else "binary",
        }
    except Exception as e:
        raise GitError(f"failed to read file: {e}")
