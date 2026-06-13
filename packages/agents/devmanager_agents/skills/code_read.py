from __future__ import annotations

import asyncio
from pathlib import Path

from devmanager_agents.registry import Skill, SkillContext, SkillRegistry
from devmanager_agents.sandbox import safe_path

_MAX_READ_CHARS = 4000


async def _read_handler(args: dict, ctx: SkillContext) -> str:
    path = safe_path(ctx.repo_dir, args["path"])
    if path is None:
        return "(file not found)"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(read error: {exc})"
    lines = text.splitlines()
    start = max(1, args.get("start_line", 1)) - 1
    end = min(len(lines), args.get("end_line", len(lines)))
    chunk = "\n".join(lines[start:end])
    if len(chunk) > _MAX_READ_CHARS:
        chunk = chunk[:_MAX_READ_CHARS] + "\n... (truncated)"
    return chunk


async def _grep_handler(args: dict, ctx: SkillContext) -> str:
    pattern = args["pattern"]
    raw_path = args["path"]
    context = args.get("context", 2)
    target = ctx.repo_dir / raw_path.lstrip("/")
    if not target.exists():
        return f"(path not found: {raw_path!r})"

    async def _run(cmd: list[str]) -> str:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return stdout.decode() if stdout else ""

    out = ""
    for cmd in (
        ["rg", "-n", "--no-heading", f"-C{context}", pattern, str(target)],
        ["grep", "-rn", f"-C{context}", pattern, str(target)],
    ):
        try:
            out = await _run(cmd)
            break
        except FileNotFoundError:
            continue
    else:
        return "(no grep available)"

    out = out.strip()
    if not out:
        return "(no matches)"
    if len(out) > _MAX_READ_CHARS:
        out = out[:_MAX_READ_CHARS] + "\n... (truncated)"
    return out


async def _glob_handler(args: dict, ctx: SkillContext) -> str:
    pattern = args["pattern"]
    matches = sorted(
        str(path.relative_to(ctx.repo_dir)) for path in ctx.repo_dir.glob(pattern) if path.is_file()
    )
    if not matches:
        return "(no files matched)"
    if len(matches) > 200:
        matches = matches[:200] + ["... (truncated)"]
    return "\n".join(matches)


def _read_hunks_ref(hunks_ref: str | None) -> str:
    if not hunks_ref:
        return ""
    ref = hunks_ref.removeprefix("file://")
    diff_path = Path(ref)
    if not diff_path.exists():
        return f"(diff file not found: {ref})"
    text = diff_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > _MAX_READ_CHARS:
        text = text[:_MAX_READ_CHARS] + "\n... (truncated)"
    return text


async def _getdiff_handler(args: dict, ctx: SkillContext) -> str:
    target = args["file_path"]
    change_unit = None

    if ctx.change_units:
        for cu in ctx.change_units:
            if getattr(cu, "file_path", None) == target:
                change_unit = cu
                break

    if change_unit is None and ctx.db is not None:
        from devmanager_db.models import ChangeUnit
        from sqlalchemy import select

        stmt = select(ChangeUnit).where(ChangeUnit.file_path == target)
        if ctx.workflow_id is not None:
            stmt = stmt.where(ChangeUnit.run_id == ctx.workflow_id)
        stmt = stmt.limit(1)
        result = await ctx.db.execute(stmt)
        change_unit = result.scalar_one_or_none()

    if change_unit is None or not getattr(change_unit, "hunks_ref", None):
        return f"(no diff for {target!r})"
    return _read_hunks_ref(change_unit.hunks_ref)


def register_code_read_skills(registry: SkillRegistry) -> None:
    registry.register(
        Skill(
            name="Read",
            description=(
                "Read a file from the repository. Optionally specify start_line and "
                "end_line (1-indexed, inclusive) to read a slice. Returns the file "
                "content (truncated to 4000 chars)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "required": ["path"],
            },
            handler=_read_handler,
            requires=("repo_dir",),
            timeout_seconds=5.0,
        )
    )
    registry.register(
        Skill(
            name="Grep",
            description=(
                "Search files for a regex pattern. Returns matching lines as "
                "'<file>:<line>:<content>'. context=N adds N lines before/after each match."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "context": {"type": "integer", "default": 2, "minimum": 0, "maximum": 10},
                },
                "required": ["pattern", "path"],
            },
            handler=_grep_handler,
            requires=("repo_dir",),
            timeout_seconds=10.0,
        )
    )
    registry.register(
        Skill(
            name="Glob",
            description=(
                "Return files matching a glob pattern, relative to repo root. "
                "Example: 'src/**/*.py'"
            ),
            input_schema={
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
            handler=_glob_handler,
            requires=("repo_dir",),
            timeout_seconds=5.0,
        )
    )
    registry.register(
        Skill(
            name="GetDiff",
            description="Return the diff for a specific file in this PR.",
            input_schema={
                "type": "object",
                "properties": {"file_path": {"type": "string"}},
                "required": ["file_path"],
            },
            handler=_getdiff_handler,
            requires=("repo_dir", "db"),
            timeout_seconds=5.0,
        )
    )
