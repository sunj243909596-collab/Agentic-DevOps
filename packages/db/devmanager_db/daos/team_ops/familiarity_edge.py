"""S4 P4 — FamiliarityEdgeDAO。"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import FamiliarityEdge


def compute_score(lines_changed: int, commits_count: int) -> float:
    """v1 score 公式：log10(1 + lines_changed) * log10(1 + commits_count)。

    降权：单大文件/单人高频 commit 都不应线性放大。
    """
    return round(
        math.log10(1 + max(0, lines_changed)) * math.log10(1 + max(0, commits_count)),
        3,
    )


class FamiliarityEdgeDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        person_id: uuid.UUID,
        area_key: str,
        commits_count: int,
        lines_changed: int,
    ) -> None:
        score = compute_score(lines_changed, commits_count)
        stmt = (
            pg_insert(FamiliarityEdge)
            .values(
                person_id=person_id,
                area_key=area_key,
                commits_count=commits_count,
                lines_changed=lines_changed,
                score=score,
                last_seen_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["person_id", "area_key"],
                set_={
                    "commits_count": commits_count,
                    "lines_changed": lines_changed,
                    "score": score,
                    "last_seen_at": datetime.now(UTC),
                },
            )
        )
        await self._session.execute(stmt)

    async def list_by_person(
        self,
        person_id: uuid.UUID,
    ) -> list[FamiliarityEdge]:
        result = await self._session.execute(
            select(FamiliarityEdge)
            .where(FamiliarityEdge.person_id == person_id)
            .order_by(FamiliarityEdge.score.desc())
        )
        return list(result.scalars().all())

    async def top_across_people(
        self,
        *,
        area_key: str,
        limit: int = 20,
    ) -> list[FamiliarityEdge]:
        """v1 帮助接口：按 area_key 找最熟的人（top N），后续 S2 用。"""
        result = await self._session.execute(
            select(FamiliarityEdge)
            .where(FamiliarityEdge.area_key == area_key)
            .order_by(FamiliarityEdge.score.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
