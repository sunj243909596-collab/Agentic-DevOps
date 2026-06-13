"""End-to-end integration test for agent review_run pipeline.

Requires a live PostgreSQL instance (see tests/integration/conftest.py).
The LLM provider is stubbed; skills and DB persistence run for real.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from devmanager_agents.service import review_run
from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.change_unit import ChangeUnitDAO
from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.daos.team_ops.knowledge_chunk import KnowledgeChunkDAO
from devmanager_db.daos.team_ops.knowledge_document import KnowledgeDocumentDAO
from devmanager_db.models import (
    AnalysisRun,
    AuditEvent,
    ChangeUnit,
    Finding,
    KnowledgeChunk,
    KnowledgeDocument,
    Repository,
)
from devmanager_llm import LLMResponse
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

_VALID_CATEGORIES = {
    "correctness",
    "security",
    "testing",
    "maintainability",
    "performance",
}


class StubProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="",
                model="stub",
                tool_uses=[
                    {
                        "id": "t1",
                        "name": "GetDiff",
                        "input": {"file_path": "a.py"},
                    }
                ],
                stop_reason="tool_use",
            )
        return LLMResponse(
            content=json.dumps(
                [
                    {
                        "category": "correctness",
                        "severity": "high",
                        "confidence": 0.9,
                        "file": "a.py",
                        "start_line": 10,
                        "end_line": 12,
                        "observation": "Potential logic error in assignment",
                        "impact": "Runtime failure under edge conditions",
                        "recommendation": "Add guard before assignment",
                        "verification": "Run unit test covering this branch",
                        "evidence_refs": ["diff:a.py:10-12"],
                    }
                ]
            ),
            model="stub",
            tool_uses=[],
            stop_reason="end_turn",
        )


@pytest_asyncio.fixture
async def e2e_setup(tmp_path: Path, session: AsyncSession) -> dict:
    today = datetime.now(UTC).strftime("%Y%m%d")
    stale_finding_id = f"F-{today}-001"
    stale = await session.execute(delete(Finding).where(Finding.finding_id == stale_finding_id))
    if stale.rowcount:
        await session.commit()

    repo_dao = RepositoryDAO(session)
    run_dao = AnalysisRunDAO(session)
    cu_dao = ChangeUnitDAO(session)
    doc_dao = KnowledgeDocumentDAO(session)
    chunk_dao = KnowledgeChunkDAO(session)

    repo = await repo_dao.create(
        provider="gitlab",
        full_name=f"e2e-org/repo-{uuid.uuid4().hex[:6]}",
        clone_url="https://gitlab.example.com/e2e/repo.git",
    )
    run = await run_dao.create(
        repository_id=repo.repository_id,
        repository_full_name=repo.full_name,
        trigger_type="push",
        target_branch="main",
        baseline_sha="0" * 40,
        target_sha="a" * 40,
        status="trigger_received",
        policy_version="v1",
        scoring_version="v1",
    )

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "a.py").write_text("x = 1\n" * 10, encoding="utf-8")

    diff_file = tmp_path / "a.py.diff"
    diff_file.write_text("+x = 1\n+y = 2\n+z = 3\n+w = 4\n+v = 5\n", encoding="utf-8")

    units = await cu_dao.bulk_create(
        [
            {
                "run_id": run.run_id,
                "repository_full_name": repo.full_name,
                "baseline_sha": run.baseline_sha,
                "target_sha": run.target_sha,
                "file_path": "a.py",
                "change_type": "modified",
                "language": "python",
                "added_lines": 10,
                "deleted_lines": 0,
                "is_binary": False,
                "is_generated": False,
                "is_vendor": False,
                "risk_tags": [],
                "hunks_ref": f"file://{diff_file}",
            }
        ]
    )

    doc = await doc_dao.create(source="prd", title="k-e2e")
    await chunk_dao.create(
        document_id=doc.document_id,
        chunk_index=0,
        content="k content",
        token_count=2,
        embedding=[0.5] + [0.0] * 1535,
    )

    await session.commit()

    return {
        "run_id": run.run_id,
        "repo_dir": repo_dir,
        "cu": units[0],
        "repo": repo,
        "kb_doc_id": doc.document_id,
    }


@pytest.mark.asyncio
async def test_e2e_review_run_produces_finding_in_5_dimensions(
    session: AsyncSession,
    e2e_setup: dict,
) -> None:
    provider = StubProvider()
    findings = await review_run(
        e2e_setup["run_id"],
        session,
        provider,
        repo_dir=e2e_setup["repo_dir"],
        concurrency=1,
    )

    assert len(findings) >= 1
    finding = findings[0]
    assert finding.category in _VALID_CATEGORIES
    assert finding.evidence_refs
    assert provider.calls >= 2

    run_id = e2e_setup["run_id"]
    repo_id = e2e_setup["repo"].repository_id
    kb_doc_id = e2e_setup["kb_doc_id"]

    await session.execute(delete(Finding).where(Finding.run_id == run_id))
    await session.execute(delete(AuditEvent).where(AuditEvent.workflow_id == run_id))
    await session.execute(delete(ChangeUnit).where(ChangeUnit.run_id == run_id))
    await session.execute(delete(AnalysisRun).where(AnalysisRun.run_id == run_id))
    await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == kb_doc_id))
    await session.execute(
        delete(KnowledgeDocument).where(KnowledgeDocument.document_id == kb_doc_id)
    )
    await session.execute(delete(Repository).where(Repository.repository_id == repo_id))
    await session.commit()
