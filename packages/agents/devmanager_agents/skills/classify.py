from __future__ import annotations

import hashlib
import json
import time

from devmanager_agents.registry import Skill, SkillContext, SkillRegistry

CLASSIFY_SYSTEM = """You classify code changes. Given a file path and a diff excerpt, return JSON:
{"type": "api"|"data"|"ui"|"script"|"config"|"test"|"other",
 "focus_dimensions": [
   "correctness","security","testing","maintainability","performance"
 ]}

Rules:
- "api" if the file defines HTTP endpoints, RPC, or service interfaces
- "data" if the file is a migration, schema, ORM model, or query
- "ui" if the file is a component, view, template, or stylesheet
- "test" if the file is a *_test.go or test_*.py
- "config" if the file is CI, infra, or build config
- focus_dimensions: include the 2-3 most relevant dimensions (always include "correctness")

Output ONLY the JSON object."""

_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 3600.0


def _cache_key(file_path: str, diff_sha: str) -> str:
    return f"classify:{file_path}:{diff_sha}"


async def _classify_handler(args: dict, ctx: SkillContext) -> str:
    if ctx.provider is None:
        return json.dumps(
            {
                "type": "other",
                "focus_dimensions": ["correctness"],
            }
        )
    file_path = args["file_path"]
    diff_sha = args.get(
        "diff_sha",
        hashlib.sha1(args.get("diff_excerpt", "").encode()).hexdigest()[:12],
    )
    key = _cache_key(file_path, diff_sha)
    now = time.time()
    if key in _CACHE and (now - _CACHE[key][0]) < _CACHE_TTL:
        return _CACHE[key][1]
    from devmanager_llm import LLMMessage

    resp = await ctx.provider.complete(
        messages=[
            LLMMessage(
                role="user",
                content=f"file: {file_path}\n\ndiff:\n{args.get('diff_excerpt', '')[:2000]}",
            )
        ],
        system=CLASSIFY_SYSTEM,
        max_tokens=200,
        temperature=0.0,
    )
    result = resp.content.strip()
    _CACHE[key] = (now, result)
    return result


def register_classify_skill(registry: SkillRegistry) -> None:
    registry.register(
        Skill(
            name="classify_change",
            description=(
                "Classify a code change by type and focus dimensions. Returns JSON with "
                "type and focus_dimensions array. Used at the start of review to adapt focus."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "diff_excerpt": {"type": "string"},
                    "diff_sha": {
                        "type": "string",
                        "description": "Optional: SHA of diff for cache key",
                    },
                },
                "required": ["file_path", "diff_excerpt"],
            },
            handler=_classify_handler,
            requires=("provider",),
            timeout_seconds=20.0,
        )
    )
