from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from devmanager_git.fetcher import _EMPTY_TREE, GitError

_MAX_HUNK_BYTES = 512 * 1024  # 512 KB per file — skip larger diffs


def _diff_file(repo_dir: Path, from_ref: str, to_ref: str, file_path: str) -> str:
    args = ["git", "diff", "--patch", from_ref, to_ref, "--", file_path]
    if from_ref == _EMPTY_TREE:
        args = ["git", "diff", "--patch", _EMPTY_TREE, to_ref, "--", file_path]
    result = subprocess.run(args, cwd=repo_dir, capture_output=True)
    if result.returncode != 0:
        raise GitError(result.stderr.decode(errors="replace").strip())
    return result.stdout.decode(errors="replace")


async def extract_hunk(
    repo_dir: Path,
    from_ref: str,
    to_ref: str,
    file_path: str,
    output_path: Path,
) -> str | None:
    """
    Extract diff patch for one file and write to output_path.
    Returns the output path string (as hunks_ref) or None if patch is empty.
    """
    loop = asyncio.get_event_loop()
    try:
        patch = await loop.run_in_executor(
            None, _diff_file, repo_dir, from_ref, to_ref, file_path
        )
    except GitError:
        return None

    if not patch.strip():
        return None

    if len(patch.encode()) > _MAX_HUNK_BYTES:
        # Store a placeholder noting the patch was too large
        patch = f"# PATCH_TOO_LARGE: {file_path} ({len(patch.encode())} bytes)\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patch, encoding="utf-8")
    return f"file://{output_path}"


async def extract_all_hunks(
    repo_dir: Path,
    from_ref: str,
    to_ref: str,
    units: list[dict],
    hunks_dir: Path,
) -> dict[str, str]:
    """
    Extract hunks for all non-binary ChangeUnit dicts concurrently.
    Returns {change_unit_id_str: hunks_ref}.
    """
    sem = asyncio.Semaphore(8)

    async def _one(unit: dict) -> tuple[str, str | None]:
        if unit.get("is_binary") or unit.get("is_generated") or unit.get("is_vendor"):
            return str(unit["change_unit_id"]), None
        file_path = unit["file_path"]
        out_path = hunks_dir / f"{unit['change_unit_id']}.diff"
        async with sem:
            ref = await extract_hunk(repo_dir, from_ref, to_ref, file_path, out_path)
        return str(unit["change_unit_id"]), ref

    results = await asyncio.gather(*[_one(u) for u in units])
    return {cu_id: ref for cu_id, ref in results if ref is not None}
