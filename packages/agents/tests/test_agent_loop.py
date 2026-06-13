import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from devmanager_agents.agent_reviewer import AgentReviewer
from devmanager_agents.skills import default_registry
from devmanager_llm import LLMResponse


def _make_cu(file_path: str = "a.py") -> MagicMock:
    m = MagicMock()
    m.file_path = file_path
    m.language = "python"
    m.change_type = "modified"
    m.risk_tags = []
    m.added_lines = 10
    m.deleted_lines = 0
    m.hunks_ref = None
    m.repository_full_name = "org/repo"
    return m


def _make_provider(responses: list[LLMResponse]):
    p = MagicMock()
    p.name = "mock"
    p.complete = AsyncMock(side_effect=responses)
    return p


@pytest.mark.asyncio
async def test_agent_loop_exits_on_end_turn_with_empty_findings(tmp_path: Path):
    cu = _make_cu()
    diff = tmp_path / "x.diff"
    diff.write_text("+x = 1\n")
    cu.hunks_ref = f"file://{diff}"
    provider = _make_provider(
        [
            LLMResponse(
                content="",
                model="m",
                tool_uses=[{"id": "t1", "name": "GetDiff", "input": {"file_path": "a.py"}}],
                stop_reason="tool_use",
            ),
            LLMResponse(content="[]", model="m", tool_uses=[], stop_reason="end_turn"),
        ]
    )
    r = AgentReviewer(provider, default_registry(), max_iter=5)
    out = await r.review_all([cu], repo_dir=tmp_path)
    assert out == []


@pytest.mark.asyncio
async def test_agent_loop_respects_max_iter(tmp_path: Path):
    cu = _make_cu()
    diff = tmp_path / "x.diff"
    diff.write_text("+x = 1\n")
    cu.hunks_ref = f"file://{diff}"
    responses = [
        LLMResponse(
            content="",
            model="m",
            tool_uses=[{"id": f"t{i}", "name": "GetDiff", "input": {"file_path": "a.py"}}],
            stop_reason="tool_use",
        )
        for i in range(8)
    ]
    provider = _make_provider(responses)
    r = AgentReviewer(provider, default_registry(), max_iter=3)
    out = await r.review_all([cu], repo_dir=tmp_path)
    assert out == []
    assert provider.complete.await_count == 3


@pytest.mark.asyncio
async def test_agent_loop_extracts_findings_from_end_turn(tmp_path: Path):
    cu = _make_cu()
    diff = tmp_path / "x.diff"
    diff.write_text("+x = 1\n")
    cu.hunks_ref = f"file://{diff}"
    finding_json = json.dumps(
        [
            {
                "category": "correctness",
                "severity": "medium",
                "confidence": 0.8,
                "file": "a.py",
                "start_line": 1,
                "end_line": 1,
                "observation": "x",
                "impact": "x",
                "recommendation": "x",
                "verification": "x",
                "evidence_refs": ["diff:a.py:1-1"],
            }
        ]
    )
    provider = _make_provider(
        [
            LLMResponse(
                content="",
                model="m",
                tool_uses=[{"id": "t1", "name": "GetDiff", "input": {"file_path": "a.py"}}],
                stop_reason="tool_use",
            ),
            LLMResponse(content=finding_json, model="m", tool_uses=[], stop_reason="end_turn"),
        ]
    )
    r = AgentReviewer(provider, default_registry(), max_iter=5)
    out = await r.review_all([cu], repo_dir=tmp_path)
    assert len(out) == 1
    assert out[0]["file"] == "a.py"
    assert out[0]["category"] == "correctness"
