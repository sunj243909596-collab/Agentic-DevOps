from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Skill:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Awaitable[str]]
    requires: tuple[str, ...] = ()
    timeout_seconds: float | None = None


@dataclass
class SkillContext:
    repo_dir: Path
    db: Any | None = None
    audit_dao: Any | None = None
    workflow_id: Any | None = None
    kb: Any | None = None
    provider: Any | None = None
    linter: Any | None = None
    pr_fetcher: Any | None = None
    change_units: Any | None = None
    timeout_seconds: float = 30.0


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if not inspect.iscoroutinefunction(skill.handler):
            raise ValueError(
                f"skill {skill.name!r} handler must be async"
            )
        if skill.name in self._skills:
            raise ValueError(
                f"skill {skill.name!r} already registered"
            )
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError(f"skill {name!r} not registered")
        return self._skills[name]

    def list(self) -> list[Skill]:  # type: ignore[valid-type]
        # Method name shadows builtin `list`; mypy 2.x misresolves the
        # `list[Skill]` return annotation as the method itself. Renaming
        # would break the public plan API (test_registry.py:75), so we
        # suppress here. The annotation is correct at runtime.
        return list(self._skills.values())

    def register_many(self, skills) -> None:
        for s in skills:
            self.register(s)

    def unregister(self, name: str) -> bool:
        return self._skills.pop(name, None) is not None

    def replace(self, skill: Skill) -> None:
        if not inspect.iscoroutinefunction(skill.handler):
            raise ValueError(
                f"skill {skill.name!r} handler must be async"
            )
        self._skills[skill.name] = skill

    def to_tool_definitions(self) -> list[dict]:  # type: ignore[valid-type]
        # `list` annotation collides with `SkillRegistry.list` method
        # (see comment on the list method above).
        return [
            {
                "name": s.name,
                "description": s.description,
                "input_schema": s.input_schema,
            }
            for s in self._skills.values()
        ]

    async def execute(self, name: str, args: dict, ctx: SkillContext) -> str:
        skill = self.get(name)
        timeout = skill.timeout_seconds or ctx.timeout_seconds
        try:
            return await asyncio.wait_for(skill.handler(args, ctx), timeout=timeout)
        except TimeoutError:
            log.warning("skill %r timed out after %ss", name, timeout)
            return f"(skill timeout after {timeout}s: {name!r})"
        except Exception as exc:
            log.warning("skill %r failed: %s", name, exc)
            return f"(skill error: {type(exc).__name__}: {exc})"
