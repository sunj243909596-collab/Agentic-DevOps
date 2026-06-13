import inspect
from dataclasses import fields

import pytest
from devmanager_llm import ClaudeProvider, LLMMessage, LLMResponse, MockProvider


def test_claude_complete_is_async():
    """After Phase 1.4, complete() must be async (so asyncio.gather works)."""
    assert inspect.iscoroutinefunction(ClaudeProvider.complete), (
        "ClaudeProvider.complete must be async to not block the event loop"
    )


def test_llm_response_has_tool_uses_field():
    names = {f.name for f in fields(LLMResponse)}
    assert "tool_uses" in names, "LLMResponse must expose tool_uses list for agent loop"


def test_claude_complete_accepts_tools_kwarg():
    sig = inspect.signature(ClaudeProvider.complete)
    assert "tools" in sig.parameters, "ClaudeProvider.complete must accept tools= parameter"


@pytest.mark.asyncio
async def test_mock_provider_returns_tool_use_then_end():
    """Mock scenario='agent' should return a tool_use first, then end_turn."""
    p = MockProvider(scenario="agent")
    r1 = await p.complete(
        messages=[LLMMessage(role="user", content="review a.py")],
        tools=[{"name": "Read", "description": "x", "input_schema": {}}],
    )
    assert r1.stop_reason == "tool_use"
    assert any(t["name"] == "Read" for t in r1.tool_uses)
    r2 = await p.complete(messages=[LLMMessage(role="user", content="got result")], tools=[])
    assert r2.stop_reason == "end_turn"
    assert r2.content.strip().startswith("[")
