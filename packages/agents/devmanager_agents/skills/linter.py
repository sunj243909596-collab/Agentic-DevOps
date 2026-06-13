from __future__ import annotations

import asyncio

from devmanager_agents.registry import Skill, SkillContext, SkillRegistry
from devmanager_agents.sandbox import safe_path


async def _run_linter_handler(args: dict, ctx: SkillContext) -> str:
    file_path = args["file_path"]
    linter_name = args.get("linter")
    config = ctx.linter
    if not config or linter_name is None:
        return "(linter not configured for this project)"
    cmd_template = config.get(linter_name)
    if not cmd_template:
        return f"(no linter named {linter_name!r})"
    path = safe_path(ctx.repo_dir, file_path)
    if path is None:
        return f"(file not found: {file_path!r})"
    cmd = list(cmd_template) + [str(path)]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    except FileNotFoundError as exc:
        return f"(linter not found: {exc})"
    except TimeoutError:
        return "(linter timeout after 60s)"
    out = (stdout.decode() if stdout else "") + (stderr.decode() if stderr else "")
    return out.strip() or f"(no output, exit {proc.returncode})"


def register_linter_skill(registry: SkillRegistry) -> None:
    registry.register(
        Skill(
            name="run_linter",
            description=(
                "Run a configured linter on a file. The linter name and command must be "
                "pre-configured in the project's linter config (injected via SkillContext.linter)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "linter": {
                        "type": "string",
                        "description": "Linter name (e.g. 'python', 'go', 'eslint')",
                    },
                },
                "required": ["file_path", "linter"],
            },
            handler=_run_linter_handler,
            requires=("repo_dir", "linter"),
            timeout_seconds=60.0,
        )
    )
