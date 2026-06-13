from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from devmanager_agents.kb import KnowledgeBase
from devmanager_db.daos.team_ops.knowledge_chunk import KnowledgeChunkDAO
from devmanager_db.daos.team_ops.knowledge_document import KnowledgeDocumentDAO
from devmanager_db.models import KnowledgeChunk, KnowledgeDocument
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


class FakeEmbedder:
    def __init__(self, vec: list[float]) -> None:
        self._vec = vec

    @property
    def dimensions(self) -> int:
        return len(self._vec)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec for _ in texts]


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    yield
    await session.rollback()
    await session.execute(delete(KnowledgeChunk))
    await session.execute(delete(KnowledgeDocument))
    await session.commit()


@pytest.mark.asyncio
async def test_search_returns_top_k_with_similarity(session: AsyncSession, cleanup: None) -> None:
    doc_dao = KnowledgeDocumentDAO(session)
    chunk_dao = KnowledgeChunkDAO(session)
    doc = await doc_dao.create(source="prd", title="test-doc")
    await chunk_dao.create(
        document_id=doc.document_id,
        chunk_index=0,
        content="alpha content",
        token_count=2,
        embedding=[1.0, 0.0, 0.0] + [0.0] * 1533,
    )
    await chunk_dao.create(
        document_id=doc.document_id,
        chunk_index=1,
        content="beta content",
        token_count=2,
        embedding=[0.0, 1.0, 0.0] + [0.0] * 1533,
    )
    kb = KnowledgeBase(
        session,
        FakeEmbedder([0.9, 0.1, 0.0] + [0.0] * 1533),
        min_similarity=0.5,
    )
    hits = await kb.search("query", top_k=1)
    assert len(hits) == 1
    assert hits[0]["content"] == "alpha content"
    assert hits[0]["score"] > 0.5


@pytest.mark.asyncio
async def test_lookup_rule_finds_by_title(session: AsyncSession, cleanup: None) -> None:
    doc_dao = KnowledgeDocumentDAO(session)
    await doc_dao.create(source="coding_rule", title="JAVA_NAMING_001")
    kb = KnowledgeBase(session, FakeEmbedder([0.0] * 1536))
    result = await kb.lookup_rule("JAVA_NAMING_001")
    assert result is not None
    assert result["source_ref"] == "rule:JAVA_NAMING_001"


@pytest.mark.asyncio
async def test_ingest_creates_doc_with_chunks(session: AsyncSession, cleanup: None) -> None:
    kb = KnowledgeBase(session, FakeEmbedder([0.1] * 1536))
    doc_id = await kb.ingest(
        source="prd",
        title="ingest-test",
        version="1.0",
        chunks=["chunk one", "chunk two"],
    )
    assert doc_id is not None
    chunks = await KnowledgeChunkDAO(session).list_by_document(doc_id)
    assert {c.chunk_index for c in chunks} == {0, 1}
    assert chunks[0].embedding is not None


@pytest.mark.asyncio
async def test_search_filters_below_min_similarity(session: AsyncSession, cleanup: None) -> None:
    doc_dao = KnowledgeDocumentDAO(session)
    chunk_dao = KnowledgeChunkDAO(session)
    doc = await doc_dao.create(source="prd", title="t")
    await chunk_dao.create(
        document_id=doc.document_id,
        chunk_index=0,
        content="orthogonal",
        token_count=1,
        embedding=[1.0, 0.0] + [0.0] * 1534,
    )
    kb = KnowledgeBase(
        session,
        FakeEmbedder([0.0, 1.0] + [0.0] * 1534),
        min_similarity=0.5,
    )
    hits = await kb.search("q", top_k=5)
    assert hits == []
