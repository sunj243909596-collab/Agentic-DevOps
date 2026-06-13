from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath


class CodeownersParser:
    """
    Parses GitHub-style CODEOWNERS files.
    Rules are evaluated last-to-first (last matching pattern wins).
    """

    def __init__(self, rules: list[tuple[str, str]]) -> None:
        # rules: list of (pattern, owner_string) in file order
        self._rules = rules

    @classmethod
    def from_text(cls, text: str) -> CodeownersParser:
        rules: list[tuple[str, str]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            owners = " ".join(parts[1:])
            rules.append((pattern, owners))
        return cls(rules)

    @classmethod
    def from_repo(cls, repo_dir: Path) -> CodeownersParser | None:
        candidates = [
            repo_dir / "CODEOWNERS",
            repo_dir / ".github" / "CODEOWNERS",
            repo_dir / "docs" / "CODEOWNERS",
        ]
        # In a bare repo, paths are relative to the root
        for candidate in candidates:
            if candidate.exists():
                return cls.from_text(candidate.read_text(encoding="utf-8", errors="replace"))
        return None

    @classmethod
    def from_bare_repo(cls, repo_dir: Path) -> CodeownersParser | None:
        """Read CODEOWNERS from a bare/mirror git repo using git show."""
        import subprocess

        for ref_path in ["HEAD:CODEOWNERS", "HEAD:.github/CODEOWNERS", "HEAD:docs/CODEOWNERS"]:
            result = subprocess.run(
                ["git", "show", ref_path],
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return cls.from_text(result.stdout)
        return None

    def find_owner(self, file_path: str) -> str | None:
        """Return the owner string for file_path (last matching rule wins)."""
        # Normalise to forward slashes, no leading slash
        fp = str(PurePosixPath(file_path))
        matched: str | None = None
        for pattern, owner in self._rules:
            if self._matches(pattern, fp):
                matched = owner
        return matched

    @staticmethod
    def _matches(pattern: str, file_path: str) -> bool:
        # Strip leading / from pattern for matching
        p = pattern.lstrip("/")

        # Directory pattern (ends with /)
        if p.endswith("/"):
            return file_path.startswith(p) or ("/" + p) in file_path

        # If pattern contains no slash, match against basename only
        if "/" not in p:
            basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
            return fnmatch.fnmatch(basename, p)

        # Otherwise do full path fnmatch (with ** → * for simplicity)
        p_glob = p.replace("**", "*")
        return fnmatch.fnmatch(file_path, p_glob) or fnmatch.fnmatch("/" + file_path, "/" + p_glob)
