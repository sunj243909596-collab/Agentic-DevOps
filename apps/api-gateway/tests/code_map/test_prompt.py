# apps/api-gateway/tests/code_map/test_prompt.py
from __future__ import annotations

from api_gateway.routers.code_map.prompt import SYSTEM_PROMPT, build_messages
from api_gateway.routers.code_map.schema import Module, ScopeGraph


def test_system_prompt_is_non_empty_string():
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 200


def test_build_messages_with_existing_graph():
    old = ScopeGraph(
        scope="apps",
        version=3,
        generated_at="t",
        head_sha="abc",
        generator="x",
        modules=[Module(id="apps/web", path="apps/web", name="Web")],
    )
    messages = build_messages(
        scope="apps",
        old_graph=old,
        changed_files=["apps/web/src/pages/Settings.tsx"],
        file_tree="- apps/web/src/pages/Settings.tsx\n- apps/web/src/main.tsx",
    )
    assert len(messages) == 1
    user = messages[0].content
    assert "apps/web" in user
    assert "Settings.tsx" in user
    assert '"version": 3' in user or '"version":3' in user  # old graph echoed


def test_build_messages_without_old_graph_v0():
    messages = build_messages(
        scope="apps",
        old_graph=None,
        changed_files=[],
        file_tree="- apps/web/src/main.tsx",
    )
    assert "v0" in messages[0].content or "no prior" in messages[0].content.lower()


def test_build_messages_truncates_huge_tree():
    huge = "\n".join(f"- file_{i}.ts" for i in range(5000))
    messages = build_messages(scope="apps", old_graph=None, changed_files=[], file_tree=huge)
    assert "truncated" in messages[0].content
    # Should be well under 100KB
    assert len(messages[0].content) < 100_000
