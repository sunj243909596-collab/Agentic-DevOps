from __future__ import annotations

from devmanager_agents.registry import Skill, SkillContext, SkillRegistry


async def _lookup_rule_handler(args: dict, ctx: SkillContext) -> str:
    if ctx.kb is None:
        return "(knowledge base not configured)"
    rule = await ctx.kb.lookup_rule(args["rule_id"])
    if rule is None:
        return f"(no rule found: {args['rule_id']!r})"
    return (
        f"Rule: {rule['title']}\n"
        f"source_ref: {rule['source_ref']}\n"
        f"(call search_knowledge with query=this rule to read full text)"
    )


def register_rule_lookup_skill(registry: SkillRegistry) -> None:
    registry.register(
        Skill(
            name="lookup_rule",
            description=(
                "Look up a coding rule by its rule_id (exact match). Returns the rule "
                "title and a source_ref for citation."
            ),
            input_schema={
                "type": "object",
                "properties": {"rule_id": {"type": "string"}},
                "required": ["rule_id"],
            },
            handler=_lookup_rule_handler,
            requires=("kb",),
            timeout_seconds=5.0,
        )
    )
