"""LLM provider abstraction — pluggable backends for review / scoring / reporting.

The agent layer depends on this module only, never on a specific provider SDK.
Add a new provider by implementing the `LLMProvider` protocol and registering
it in `PROVIDERS`.

Currently supported:
  - claude  (Anthropic Claude via official SDK)
  - mock    (returns canned response; for demos / CI without API key)

Adding a new provider is a 3-step change:
  1. Subclass `LLMProvider` (or satisfy the Protocol) in a new file
  2. Register it: `PROVIDERS["openai"] = OpenAIProvider`
  3. Set `llm_provider=openai` in the settings table
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


# ── Public types ──────────────────────────────────────────────────────────────

@dataclass
class LLMMessage:
    role: str       # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, int] | None = None
    raw: Any = None
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = None


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse: ...


class LLMAuthError(Exception):
    """Raised when the provider is missing credentials (e.g. no API key)."""


def run_complete(
    provider: LLMProvider,
    messages: list[LLMMessage],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    system: str | None = None,
    tools: list[dict] | None = None,
) -> LLMResponse:
    """Sync wrapper for callers without an event loop (e.g. code-map regen)."""
    return asyncio.run(
        provider.complete(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            tools=tools,
        )
    )


# ── Claude provider ──────────────────────────────────────────────────────────

class ClaudeProvider:
    name = "claude"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise LLMAuthError("Claude API key is empty — set it in 系统设置 → LLM")
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "").strip() or None
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise LLMAuthError("anthropic SDK not installed; pip install anthropic") from e
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
            log.info("claude provider using custom base_url=%s", self._base_url)
        self._client = Anthropic(**client_kwargs)

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        return await asyncio.to_thread(
            self._complete_sync,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            tools=tools,
        )

    def _complete_sync(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int,
        temperature: float,
        system: str | None,
        tools: list[dict] | None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages if m.role != "system"
            ],
        }
        if tools:
            kwargs["tools"] = tools
        if system:
            kwargs["system"] = system
        elif messages and messages[0].role == "system":
            kwargs["system"] = messages[0].content
            kwargs["messages"] = [{"role": m.role, "content": m.content} for m in messages[1:]]
        r = self._client.messages.create(**kwargs)
        text = "".join(block.text for block in r.content if getattr(block, "type", "") == "text")
        tool_uses = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in r.content if getattr(b, "type", "") == "tool_use"
        ]
        return LLMResponse(
            content=text,
            model=r.model,
            usage=(
                {"input": r.usage.input_tokens, "output": r.usage.output_tokens}
                if r.usage else None
            ),
            raw=r,
            tool_uses=tool_uses,
            stop_reason=r.stop_reason,
        )


# ── Mock provider (no API needed; for demos + local dev) ────────────────────

class MockProvider:
    """Returns a canned response. Default scenario is `findings` (review-agent
    shape: `{"findings": []}`). Other scenarios are useful for verifying other
    pipelines end-to-end without a real LLM:

    - `findings`  → `{"findings": []}` (default; what the review agent expects)
    - `codemap`   → a minimal valid `ScopeGraph` JSON, derived from the scope
                    name embedded in the user message
    - `agent`     → tool_use on first call, end_turn with `[]` on second
    """

    name = "mock"

    def __init__(self, model: str = "mock-noop", scenario: str | None = None) -> None:
        self._model = model
        self._scenario = scenario or os.getenv("LLM_MOCK_SCENARIO", "findings")
        self._call_count = 0

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        if self._scenario == "agent":
            self._call_count += 1
            if self._call_count == 1:
                return LLMResponse(
                    content="",
                    model=self._model,
                    usage={"input": 0, "output": 0},
                    tool_uses=[{"id": "t1", "name": "Read", "input": {"path": "a.py"}}],
                    stop_reason="tool_use",
                )
            return LLMResponse(
                content="[]",
                model=self._model,
                usage={"input": 0, "output": 0},
                tool_uses=[],
                stop_reason="end_turn",
            )
        if self._scenario == "codemap":
            content = _build_codemap_mock(messages)
        else:
            content = '{"findings": []}'
        return LLMResponse(
            content=content,
            model=self._model,
            usage={"input": 0, "output": 0},
            stop_reason="end_turn",
        )


def _build_codemap_mock(messages: list[LLMMessage]) -> str:
    """Parse the scope name out of the user message and return a valid
    ScopeGraph JSON. Module list is empty — regen falls back to "preserve
    old" only when no old graph exists; the disk index will show the scope
    with `module_count=0` until a real LLM populates it. The point of this
    mock is to exercise the disk-write + index-update + store paths.
    """
    scope = "unknown"
    for m in messages:
        if m.role == "user":
            for line in m.content.splitlines():
                if line.startswith("scope = "):
                    scope = line.split("=", 1)[1].strip()
                    break
            break
    payload = {
        "scope": scope,
        "version": 1,
        "generated_at": "1970-01-01T00:00:00Z",
        "head_sha": "mock",
        "generator": "mock-codemap",
        "modules": [],
        "edges": [],
    }
    return json.dumps(payload, ensure_ascii=False)


# ── Provider registry ───────────────────────────────────────────────────────

PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "mock":   MockProvider,
}


def make_provider(
    name: str,
    *,
    api_key: str = "",
    model: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Factory: instantiate the named provider.

    Args:
        name: provider key from `PROVIDERS` (e.g. "claude", "mock")
        api_key: provider API key (empty for mock)
        model: model identifier; falls back to provider default
        base_url: custom API base URL (only honored by providers that
            support it — currently `claude`). Empty/None means "use the
            provider default".

    Raises LLMAuthError if the provider requires credentials that aren't set.
    """
    cls = PROVIDERS.get(name)
    if cls is None:
        raise LLMAuthError(
            f"unknown LLM provider: {name!r}. Available: {list(PROVIDERS)}"
        )
    if name == "claude":
        resolved_model: str
        if model:
            resolved_model = model
        else:
            resolved_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        return ClaudeProvider(
            api_key=api_key,
            model=resolved_model,
            base_url=base_url,
        )
    if name == "mock":
        return MockProvider(
            model=model or "mock-noop",
            scenario=os.getenv("LLM_MOCK_SCENARIO"),
        )
    # Future providers: forward api_key/model; mypy can't see the
    # subclass signatures through the LLMProvider Protocol.
    return cls(api_key=api_key, model=model or "")  # type: ignore[call-arg]


# ── Embedder re-exports (Phase 7.3) ─────────────────────────────────────────
from devmanager_llm.embedder import (  # noqa: E402, F401
    AzureOpenAIEmbedder,
    Embedder,
    OllamaEmbedder,
    OpenAIEmbedder,
    from_env,
)

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMResponse",
    "LLMAuthError",
    "Embedder",
    "OpenAIEmbedder",
    "AzureOpenAIEmbedder",
    "OllamaEmbedder",
    "from_env",
]
