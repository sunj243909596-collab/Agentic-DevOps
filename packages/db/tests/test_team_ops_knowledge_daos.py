from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from devmanager_db.daos.team_ops.knowledge_chunk import KnowledgeChunkDAO
from devmanager_db.daos.team_ops.knowledge_document import KnowledgeDocumentDAO
from devmanager_db.models import KnowledgeChunk, KnowledgeDocument
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def cleanup(session: AsyncSession) -> AsyncGenerator[None, None]:
    yield
    await session.rollback()
    await session.execute(delete(KnowledgeChunk))
    await session.execute(delete(KnowledgeDocument))
    await session.commit()


@pytest.mark.asyncio
async def test_create_and_get_document(session: AsyncSession, cleanup: None) -> None:
    dao = KnowledgeDocumentDAO(session)
    doc = await dao.create(source="prd", title="X", version="1.0")
    assert doc.document_id is not None
    fetched = await dao.get(doc.document_id)
    assert fetched is not None
    assert fetched.title == "X"


@pytest.mark.asyncio
async def test_chunk_create_and_list_by_doc(session: AsyncSession, cleanup: None) -> None:
    doc_dao = KnowledgeDocumentDAO(session)
    chunk_dao = KnowledgeChunkDAO(session)
    doc = await doc_dao.create(source="dev_design", title="Y")
    await chunk_dao.create(
        document_id=doc.document_id,
        chunk_index=0,
        content="hello",
        token_count=1,
    )
    await chunk_dao.create(
        document_id=doc.document_id,
        chunk_index=1,
        content="world",
        token_count=1,
    )
    chunks = await chunk_dao.list_by_document(doc.document_id)
    assert {c.chunk_index for c in chunks} == {0, 1}
