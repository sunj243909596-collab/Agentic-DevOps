from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from devmanager_agents.registry import SkillContext, SkillRegistry
from devmanager_agents.skills.code_read import register_code_read_skills
from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.change_unit import ChangeUnitDAO
from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.models import AnalysisRun, ChangeUnit, Repository
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_read_skill_returns_file_content(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello\nworld\n")
    reg = SkillRegistry()
    register_code_read_skills(reg)
    ctx = SkillContext(repo_dir=tmp_path)
    out = await reg.execute("Read", {"path": "a.py"}, ctx)
    assert "hello" in out and "world" in out


@pytest.mark.asyncio
async def test_glob_skill(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.py").write_text("y")
    (tmp_path / "c.txt").write_text("z")
    reg = SkillRegistry()
    register_code_read_skills(reg)
    ctx = SkillContext(repo_dir=tmp_path)
    out = await reg.execute("Glob", {"pattern": "*.py"}, ctx)
    assert "a.py" in out and "b.py" in out and "c.txt" not in out


@pytest.mark.asyncio
async def test_grep_skill_finds_match(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello world\nfoo bar\n")
    reg = SkillRegistry()
    register_code_read_skills(reg)
    ctx = SkillContext(repo_dir=tmp_path)
    out = await reg.execute("Grep", {"pattern": "hello", "path": "a.py"}, ctx)
    assert "hello" in out
    assert "(no matches)" not in out


@pytest.mark.asyncio
async def test_getdiff_skill_returns_diff_content(
    tmp_path: Path,
    session: AsyncSession,
) -> None:
    diff_path = tmp_path / "a.diff"
    diff_path.write_text("test diff content\n+added line\n")
    suffix = uuid.uuid4().hex[:8]

    repo_dao = RepositoryDAO(session)
    run_dao = AnalysisRunDAO(session)
    change_unit_dao = ChangeUnitDAO(session)

    repo = await repo_dao.create(provider="github", full_name=f"test-org/skills-getdiff-{suffix}")
    run = await run_dao.create(
        repository_id=repo.repository_id,
        repository_full_name=repo.full_name,
        trigger_type="manual",
        target_branch="main",
        baseline_sha="abc1234",
        target_sha="def5678",
        status="completed",
        policy_version="v1",
        scoring_version="v1",
    )
    units = await change_unit_dao.bulk_create(
        [
            {
                "run_id": run.run_id,
                "repository_full_name": repo.full_name,
                "baseline_sha": "abc1234",
                "target_sha": "def5678",
                "file_path": "a.py",
                "change_type": "modified",
                "language": "python",
                "hunks_ref": f"file://{diff_path}",
            }
        ]
    )
    await session.commit()

    try:
        reg = SkillRegistry()
        register_code_read_skills(reg)
        ctx = SkillContext(repo_dir=tmp_path, db=session, workflow_id=run.run_id)
        out = await reg.execute("GetDiff", {"file_path": "a.py"}, ctx)
        assert "test diff content" in out
    finally:
        await session.execute(
            delete(ChangeUnit).where(ChangeUnit.change_unit_id == units[0].change_unit_id)
        )
        await session.execute(delete(AnalysisRun).where(AnalysisRun.run_id == run.run_id))
        await session.execute(
            delete(Repository).where(Repository.repository_id == repo.repository_id)
        )
        await session.commit()


class _SearchEmbedder:
    @property
    def dimensions(self) -> int:
        return 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.9, 0.1] + [0.0] * 1534 for _ in texts]


class _LookupEmbedder:
    @property
    def dimensions(self) -> int:
        return 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


@pytest.mark.asyncio
async def test_search_knowledge_skill(tmp_path: Path, session: AsyncSession) -> None:
    from devmanager_agents.kb import KnowledgeBase
    from devmanager_agents.skills.knowledge import register_knowledge_skill
    from devmanager_db.daos.team_ops.knowledge_chunk import KnowledgeChunkDAO
    from devmanager_db.daos.team_ops.knowledge_document import KnowledgeDocumentDAO
    from devmanager_db.models import KnowledgeChunk, KnowledgeDocument

    doc_dao = KnowledgeDocumentDAO(session)
    chunk_dao = KnowledgeChunkDAO(session)
    doc = await doc_dao.create(source="prd", title="k-test")
    await chunk_dao.create(
        document_id=doc.document_id,
        chunk_index=0,
        content="alpha",
        token_count=1,
        embedding=[1.0, 0.0] + [0.0] * 1534,
    )
    await session.commit()

    try:
        kb = KnowledgeBase(session, _SearchEmbedder(), min_similarity=0.5)
        reg = SkillRegistry()
        register_knowledge_skill(reg)
        ctx = SkillContext(repo_dir=tmp_path, db=session, kb=kb)
        out = await reg.execute("search_knowledge", {"query": "alpha", "top_k": 1}, ctx)
        assert "alpha" in out
        assert "source_ref" in out
    finally:
        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.document_id)
        )
        await session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.document_id == doc.document_id)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_lookup_rule_skill(tmp_path: Path, session: AsyncSession) -> None:
    from devmanager_agents.kb import KnowledgeBase
    from devmanager_agents.skills.rule_lookup import register_rule_lookup_skill
    from devmanager_db.daos.team_ops.knowledge_document import KnowledgeDocumentDAO
    from devmanager_db.models import KnowledgeDocument

    doc = await KnowledgeDocumentDAO(session).create(source="coding_rule", title="RULE_001")
    await session.commit()

    try:
        kb = KnowledgeBase(session, _LookupEmbedder())
        reg = SkillRegistry()
        register_rule_lookup_skill(reg)
        ctx = SkillContext(repo_dir=tmp_path, db=session, kb=kb)
        out = await reg.execute("lookup_rule", {"rule_id": "RULE_001"}, ctx)
        assert "RULE_001" in out and "source_ref" in out
    finally:
        await session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.document_id == doc.document_id)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_classify_change_skill(tmp_path: Path) -> None:
    from devmanager_agents.skills.classify import register_classify_skill
    from devmanager_llm import LLMResponse

    class FakeProvider:
        async def complete(self, *, messages, **kwargs):
            return LLMResponse(
                content='{"type": "api", "focus_dimensions": ["correctness", "security"]}',
                model="mock",
                stop_reason="end_turn",
            )

    reg = SkillRegistry()
    register_classify_skill(reg)
    ctx = SkillContext(repo_dir=tmp_path, provider=FakeProvider())
    out = await reg.execute(
        "classify_change",
        {"file_path": "src/api/foo.py", "diff_excerpt": "+def bar(): pass"},
        ctx,
    )
    assert "api" in out
    assert "correctness" in out
    assert "security" in out


@pytest.mark.asyncio
async def test_classify_change_caches_by_file_path(tmp_path: Path) -> None:
    from devmanager_agents.skills.classify import register_classify_skill
    from devmanager_llm import LLMResponse

    call_count = 0

    class FakeProvider:
        async def complete(self, *, messages, **kwargs):
            nonlocal call_count
            call_count += 1
            return LLMResponse(
                content='{"type": "data", "focus_dimensions": ["correctness"]}',
                model="mock",
                stop_reason="end_turn",
            )

    reg = SkillRegistry()
    register_classify_skill(reg)
    ctx = SkillContext(repo_dir=tmp_path, provider=FakeProvider())
    args = {"file_path": "src/x.py", "diff_excerpt": "+a=1", "diff_sha": "abc"}
    await reg.execute("classify_change", args, ctx)
    await reg.execute("classify_change", args, ctx)
    assert call_count == 1


@pytest.mark.asyncio
async def test_run_linter_skill_invokes_subprocess(tmp_path: Path) -> None:
    from devmanager_agents.skills.linter import register_linter_skill

    (tmp_path / "a.py").write_text("x = 1")
    reg = SkillRegistry()
    register_linter_skill(reg)
    ctx = SkillContext(
        repo_dir=tmp_path,
        linter={"python": ["python", "-c", "import sys; sys.exit(0)"]},
    )
    out = await reg.execute("run_linter", {"file_path": "a.py", "linter": "python"}, ctx)
    assert "no output" in out or "exit 0" in out


@pytest.mark.asyncio
async def test_run_linter_no_config_returns_noop(tmp_path: Path) -> None:
    from devmanager_agents.skills.linter import register_linter_skill

    reg = SkillRegistry()
    register_linter_skill(reg)
    ctx = SkillContext(repo_dir=tmp_path)
    out = await reg.execute("run_linter", {"file_path": "a.py"}, ctx)
    assert "not configured" in out


@pytest.mark.asyncio
async def test_read_pr_metadata_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from devmanager_agents.skills.pr_metadata import register_pr_metadata_skill

    class FakeResp:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"title": "Add foo", "description": "Implements #123"}

    async def fake_get(self, url, **kwargs):
        return FakeResp()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    reg = SkillRegistry()
    register_pr_metadata_skill(reg)
    ctx = SkillContext(
        repo_dir=tmp_path,
        pr_fetcher={"base_url": "https://gitlab.example.com", "token": "test-token"},
    )
    out = await reg.execute("read_pr_metadata", {"pr_id": "42"}, ctx)
    assert "Add foo" in out
    assert "Implements #123" in out


def test_default_registry_has_nine_skills() -> None:
    from devmanager_agents.skills import default_registry

    reg = default_registry()
    names = {skill.name for skill in reg.list()}
    assert names == {
        "Read",
        "Grep",
        "Glob",
        "GetDiff",
        "search_knowledge",
        "lookup_rule",
        "classify_change",
        "run_linter",
        "read_pr_metadata",
    }
