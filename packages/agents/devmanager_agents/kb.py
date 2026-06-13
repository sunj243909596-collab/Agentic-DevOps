from __future__ import annotations

import uuid
from typing import Any

from devmanager_db.models import KnowledgeDocument
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


class KnowledgeBase:
    def __init__(self, db: AsyncSession, embedder: Any, *, min_similarity: float = 0.7) -> None:
        self._db = db
        self._embedder = embedder
        self._min_similarity = min_similarity

    @property
    def min_similarity(self) -> float:
        return self._min_similarity

    @min_similarity.setter
    def min_similarity(self, value: float) -> None:
        self._min_similarity = value

    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        source: str | None = None,
        repository: str | None = None,
    ) -> list[dict[str, Any]]:
        embedding = (await self._embedder.embed([query]))[0]
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        filters = [
            "1 - (c.embedding <=> CAST(:emb AS vector)) >= :min_sim",
        ]
        params: dict[str, Any] = {
            "emb": embedding_str,
            "min_sim": self._min_similarity,
            "top_k": top_k,
        }
        if source is not None:
            filters.append("d.source = :source")
            params["source"] = source
        if repository is not None:
            filters.append("d.repository = :repo")
            params["repo"] = repository
        where_clause = " AND ".join(filters)
        sql = text(f"""
            SELECT c.chunk_id, c.content, c.document_id, d.source, d.title, d.file_path,
                   1 - (c.embedding <=> CAST(:emb AS vector)) AS similarity
            FROM knowledge_chunk c
            JOIN knowledge_document d ON d.document_id = c.document_id
            WHERE {where_clause}
            ORDER BY c.embedding <=> CAST(:emb AS vector)
            LIMIT :top_k
        """)
        rows = (await self._db.execute(sql, params)).mappings().all()
        return [
            {
                "chunk_id": str(row["chunk_id"]),
                "content": row["content"],
                "document_id": str(row["document_id"]),
                "source": row["source"],
                "title": row["title"],
                "file_path": row["file_path"],
                "score": float(row["similarity"]),
                "source_ref": f"knowledge:{row['chunk_id']}",
            }
            for row in rows
        ]

    async def lookup_rule(self, rule_id: str) -> dict[str, Any] | None:
        result = await self._db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.source == "coding_rule",
                KnowledgeDocument.title == rule_id,
            )
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            return None
        return {
            "document_id": str(doc.document_id),
            "title": doc.title,
            "source_ref": f"rule:{doc.title}",
        }

    async def ingest(
        self,
        *,
        source: str,
        title: str,
        version: str | None = None,
        chunks: list[str],
        repository: str | None = None,
        file_path: str | None = None,
        language: str | None = None,
    ) -> uuid.UUID:
        from devmanager_db.daos.team_ops.knowledge_chunk import KnowledgeChunkDAO
        from devmanager_db.daos.team_ops.knowledge_document import KnowledgeDocumentDAO

        doc_dao = KnowledgeDocumentDAO(self._db)
        chunk_dao = KnowledgeChunkDAO(self._db)
        doc = await doc_dao.create(
            source=source,
            title=title,
            version=version,
            repository=repository,
            file_path=file_path,
            language=language,
        )
        embeddings = await self._embedder.embed(chunks)
        for index, (content, emb) in enumerate(zip(chunks, embeddings, strict=True)):
            await chunk_dao.create(
                document_id=doc.document_id,
                chunk_index=index,
                content=content,
                token_count=max(1, len(content) // 4),
                embedding=emb,
            )
        await self._db.commit()
        return doc.document_id
