from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import KnowledgeChunk


class KnowledgeChunkDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        chunk_index: int,
        content: str,
        token_count: int,
        embedding: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeChunk:
        row = KnowledgeChunk(
            chunk_id=uuid.uuid4(),
            document_id=document_id,
            chunk_index=chunk_index,
            content=content,
            token_count=token_count,
            embedding=embedding,
            meta=metadata or {},
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_document(self, document_id: uuid.UUID) -> list[KnowledgeChunk]:
        result = await self._session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        return list(result.scalars().all())
