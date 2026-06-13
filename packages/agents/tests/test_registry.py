import asyncio
from pathlib import Path

import pytest
from devmanager_agents.registry import Skill, SkillContext, SkillRegistry


async def dummy_handler(args, ctx):
    return "ok"


def test_skill_is_dataclass_with_required_fields():
    s = Skill(
        name="Read",
        description="Read a file",
        input_schema={"type": "object"},
        handler=dummy_handler,
    )
    assert s.name == "Read"
    assert s.description == "Read a file"
    assert s.requires == ()  # default empty
    assert s.timeout_seconds is None  # default None
    assert s.handler is dummy_handler


def test_skill_context_defaults():
    ctx = SkillContext(repo_dir=Path("/tmp"))
    assert ctx.repo_dir == Path("/tmp")
    assert ctx.db is None
    assert ctx.audit_dao is None
    assert ctx.kb is None
    assert ctx.linter is None
    assert ctx.pr_fetcher is None
    assert ctx.workflow_id is None
    assert ctx.timeout_seconds == 30.0


def test_register_succeeds():
    reg = SkillRegistry()
    s = Skill(name="X", description="", input_schema={}, handler=dummy_handler)
    reg.register(s)
    assert reg.get("X") is s


def test_register_duplicate_raises():
    reg = SkillRegistry()
    s = Skill(name="X", description="", input_schema={}, handler=dummy_handler)
    reg.register(s)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(s)


def test_register_sync_handler_raises():
    reg = SkillRegistry()

    def sync_handler(args, ctx):
        return "x"

    s = Skill(name="Y", description="", input_schema={}, handler=sync_handler)
    with pytest.raises(ValueError, match="must be async"):
        reg.register(s)


def test_get_missing_raises_keyerror():
    reg = SkillRegistry()
    with pytest.raises(KeyError):
        reg.get("NOPE")


def test_register_many():
    reg = SkillRegistry()
    s1 = Skill(name="A", description="", input_schema={}, handler=dummy_handler)
    s2 = Skill(name="B", description="", input_schema={}, handler=dummy_handler)
    reg.register_many([s1, s2])
    assert {s.name for s in reg.list()} == {"A", "B"}


def test_unregister_returns_true_when_existed():
    reg = SkillRegistry()
    reg.register(Skill(name="X", description="", input_schema={}, handler=dummy_handler))
    assert reg.unregister("X") is True
    assert reg.unregister("X") is False  # 不存在返回 False


def test_replace_overwrites_existing():
    reg = SkillRegistry()
    s1 = Skill(name="X", description="v1", input_schema={}, handler=dummy_handler)
    s2 = Skill(name="X", description="v2", input_schema={}, handler=dummy_handler)
    reg.register(s1)
    reg.replace(s2)
    assert reg.get("X").description == "v2"


def test_replace_adds_when_missing():
    reg = SkillRegistry()
    s = Skill(name="X", description="", input_schema={}, handler=dummy_handler)
    reg.replace(s)
    assert reg.get("X") is s


def test_to_tool_definitions_shape():
    reg = SkillRegistry()
    reg.register(
        Skill(
            name="Read",
            description="Read a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=dummy_handler,
        )
    )
    defs = reg.to_tool_definitions()
    assert defs == [
        {
            "name": "Read",
            "description": "Read a file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }
    ]


async def test_execute_returns_handler_result():
    async def h(args, ctx):
        return f"got {args['x']}"

    reg = SkillRegistry()
    reg.register(Skill(name="H", description="", input_schema={}, handler=h))
    out = await reg.execute("H", {"x": 1}, SkillContext(repo_dir=Path("/tmp")))
    assert out == "got 1"


async def test_execute_timeout_returns_error_string():
    async def slow(args, ctx):
        await asyncio.sleep(2)
        return "done"

    reg = SkillRegistry()
    reg.register(
        Skill(
            name="S",
            description="",
            input_schema={},
            handler=slow,
            timeout_seconds=0.1,
        )
    )
    out = await reg.execute("S", {}, SkillContext(repo_dir=Path("/tmp")))
    assert "timeout" in out.lower()


async def test_execute_exception_returns_error_string():
    async def boom(args, ctx):
        raise RuntimeError("nope")

    reg = SkillRegistry()
    reg.register(Skill(name="B", description="", input_schema={}, handler=boom))
    out = await reg.execute("B", {}, SkillContext(repo_dir=Path("/tmp")))
    assert "RuntimeError" in out and "nope" in out


async def test_execute_uses_ctx_default_timeout():
    async def slow(args, ctx):
        await asyncio.sleep(2)
        return "done"

    reg = SkillRegistry()
    reg.register(Skill(name="S", description="", input_schema={}, handler=slow))
    out = await reg.execute("S", {}, SkillContext(repo_dir=Path("/tmp"), timeout_seconds=0.1))
    assert "timeout" in out.lower()
