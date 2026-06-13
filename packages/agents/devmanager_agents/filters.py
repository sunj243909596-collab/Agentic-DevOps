from pathlib import Path

MAX_FILE_BYTES = 50_000
MIN_LINES_CHANGED = 5


def is_worth_reviewing(
    *,
    file_path: str,
    repo_dir: Path,
    is_binary: bool,
    is_generated: bool,
    is_vendor: bool,
    added_lines: int,
    deleted_lines: int,
    language: str,
) -> bool:
    """Cheap pre-filter: skip files that almost certainly won't yield findings.

    Hard rules (in order):
      1. Skip binary / generated / vendor (the caller usually pre-filters these
         too, but double-check).
      2. Skip files that don't exist on disk (e.g. deleted).
      3. Skip files larger than MAX_FILE_BYTES (50 KB) — the diff is too big
         to push verbatim to an LLM in a single shot.
      4. Skip trivial changes (< MIN_LINES_CHANGED total +/-).
    """
    if is_binary or is_generated or is_vendor:
        return False
    full = repo_dir / file_path
    if not full.exists() or not full.is_file():
        return False
    try:
        if full.stat().st_size > MAX_FILE_BYTES:
            return False
    except OSError:
        return False
    if added_lines + deleted_lines < MIN_LINES_CHANGED:
        return False
    return True
