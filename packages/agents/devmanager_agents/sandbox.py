from pathlib import Path


class SandboxError(Exception):
    """Raised when a tool request tries to escape the repo root."""


def safe_path(repo_dir: Path, requested: str) -> Path | None:
    """Resolve `requested` relative to `repo_dir`, rejecting escapes.

    Returns the resolved Path if the file exists, None if it doesn't.
    Raises SandboxError if the resolved path is outside repo_dir.
    """
    repo_root = repo_dir.resolve()
    if Path(requested).is_absolute():
        candidate = Path(requested).resolve()
    else:
        rel = requested.lstrip("/")
        candidate = (repo_dir / rel).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError as exc:
        raise SandboxError(f"path escapes repo: {requested!r}") from exc
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate
