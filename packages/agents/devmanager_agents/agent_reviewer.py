from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from devmanager_llm import LLMMessage, LLMProvider

from devmanager_agents.base import extract_json_array
from devmanager_agents.prompts import AGENT_SYSTEM_PROMPT, build_agent_user_prompt
from devmanager_agents.registry import SkillContext, SkillRegistry

log = logging.getLogger(__name__)

DEFAULT_MAX_ITER = 10


class AgentLoopMaxIter(Exception):
    """Internal signal: agent hit the iteration cap; caller should treat as 'no findings'."""


class AgentReviewer:
    """One agent review = one LLM loop, given a list of change units to review."""

    def __init__(
        self,
        provider: LLMProvider,
        registry: SkillRegistry,
        *,
        max_iter: int = DEFAULT_MAX_ITER,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._max_iter = max_iter

    async def review_all(
        self,
        change_units: list,
        *,
        repo_dir: Path,
        audit_dao=None,
        workflow_id=None,
        db=None,
    ) -> list[dict]:
        messages: list[dict] = [
            {
                "role": "user",
                "content": build_agent_user_prompt(
                    change_units,
                    repository=change_units[0].repository_full_name if change_units else "",
                ),
            },
        ]
        try:
            return await self._loop(
                messages,
                change_units,
                repo_dir,
                audit_dao=audit_dao,
                workflow_id=workflow_id,
                db=db,
            )
        except AgentLoopMaxIter:
            log.warning("agent loop hit max_iter=%d, returning []", self._max_iter)
            return []
        except Exception as exc:
            log.error("agent loop crashed: %s", exc)
            return []

    async def _loop(
        self,
        messages: list[dict],
        change_units: list,
        repo_dir: Path,
        audit_dao=None,
        workflow_id=None,
        db=None,
    ) -> list[dict]:
        ctx = SkillContext(
            repo_dir=repo_dir,
            db=db,
            audit_dao=audit_dao,
            workflow_id=workflow_id,
            provider=self._provider,
            change_units=change_units,
        )
        for _ in range(self._max_iter):
            llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]
            resp = await self._provider.complete(
                messages=llm_messages,
                max_tokens=2048,
                temperature=0.0,
                system=AGENT_SYSTEM_PROMPT,
                tools=self._registry.to_tool_definitions(),
            )
            assistant_text = resp.content
            messages.append({"role": "assistant", "content": assistant_text or ""})
            if resp.stop_reason == "end_turn" or not resp.tool_uses:
                return self._parse_findings(assistant_text)

            tool_results: list[dict] = []
            for tu in resp.tool_uses:
                try:
                    output = await self._registry.execute(
                        tu["name"],
                        tu.get("input") or {},
                        ctx,
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": output[:8000],
                        }
                    )
                    if audit_dao is not None and workflow_id is not None:
                        try:
                            await audit_dao.append(
                                actor="agent",
                                workflow_id=workflow_id,
                                event_type="agent.tool_call",
                                event_timestamp=datetime.now(UTC),
                                metadata={"tool": tu["name"], "input": tu.get("input", {})},
                            )
                        except Exception as exc:
                            log.warning("audit tool_call failed: %s", exc)
                except Exception as exc:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": f"(tool error: {exc})",
                            "is_error": True,
                        }
                    )
            messages.append({"role": "user", "content": json.dumps(tool_results)})
        raise AgentLoopMaxIter()

    @staticmethod
    def _parse_findings(text: str) -> list[dict]:
        return extract_json_array(text)
