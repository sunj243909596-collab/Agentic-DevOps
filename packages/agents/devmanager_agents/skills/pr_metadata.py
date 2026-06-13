from __future__ import annotations

import httpx

from devmanager_agents.registry import Skill, SkillContext, SkillRegistry


async def _read_pr_metadata_handler(args: dict, ctx: SkillContext) -> str:
    cfg = ctx.pr_fetcher
    if cfg is None:
        return "(PR metadata fetcher not configured)"
    base = cfg["base_url"].rstrip("/")
    token = cfg.get("token", "")
    pr_id = args["pr_id"]
    url = f"{base}/api/v4/merge_requests/{pr_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers={"PRIVATE-TOKEN": token})
        response.raise_for_status()
        data = response.json()
    return (
        f"PR #{data.get('iid', pr_id)}: {data.get('title', '')}\n"
        f"Description: {data.get('description', '')[:1000]}\n"
        f"Source branch: {data.get('source_branch', '')}\n"
        f"Target branch: {data.get('target_branch', '')}\n"
        f"Author: {data.get('author', {}).get('username', '')}"
    )


def register_pr_metadata_skill(registry: SkillRegistry) -> None:
    registry.register(
        Skill(
            name="read_pr_metadata",
            description=(
                "Fetch a PR/MR's metadata (title, description, source/target branch, author) "
                "from the configured Git provider. Returns the description so the agent can "
                "cross-reference product intent."
            ),
            input_schema={
                "type": "object",
                "properties": {"pr_id": {"type": "string"}},
                "required": ["pr_id"],
            },
            handler=_read_pr_metadata_handler,
            requires=("pr_fetcher",),
            timeout_seconds=15.0,
        )
    )
