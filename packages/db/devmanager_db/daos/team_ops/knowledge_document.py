from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import KnowledgeDocument


class KnowledgeDocumentDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        source: str,
        title: str,
        version: str | None = None,
        repository: str | None = None,
        file_path: str | None = None,
        language: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        now = datetime.now(UTC)
        row = KnowledgeDocument(
            document_id=uuid.uuid4(),
            source=source,
            title=title,
            version=version,
            repository=repository,
            file_path=file_path,
            language=language,
            meta=metadata or {},
            indexed_at=now,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, document_id: uuid.UUID) -> KnowledgeDocument | None:
        result = await self._session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.document_id == document_id)
        )
        return result.scalar_one_or_none()
