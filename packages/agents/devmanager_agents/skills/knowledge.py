from __future__ import annotations

from devmanager_agents.registry import Skill, SkillContext, SkillRegistry


async def _search_knowledge_handler(args: dict, ctx: SkillContext) -> str:
    if ctx.kb is None:
        return "(knowledge base not configured)"
    hits = await ctx.kb.search(
        args["query"],
        top_k=args.get("top_k", 5),
        source=args.get("category"),
    )
    if not hits:
        return "(no matches above similarity threshold)"
    lines = []
    for index, hit in enumerate(hits, 1):
        lines.append(
            f"[{index}] (similarity={hit['score']:.2f}) {hit['source']}: {hit['title']}\n"
            f"    {hit['content'][:300]}\n"
            f"    source_ref: {hit['source_ref']}"
        )
    return "\n\n".join(lines)


def register_knowledge_skill(registry: SkillRegistry) -> None:
    registry.register(
        Skill(
            name="search_knowledge",
            description=(
                "Search the knowledge base (PRD / dev_design / coding_rule / glossary) "
                "for content matching a query. Returns up to top_k hits with similarity "
                "scores and source_refs."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                    "category": {
                        "type": "string",
                        "enum": ["prd", "dev_design", "coding_rule", "glossary"],
                    },
                },
                "required": ["query"],
            },
            handler=_search_knowledge_handler,
            requires=("kb",),
            timeout_seconds=15.0,
        )
    )
