from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Score


class ScoreDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        run_id: uuid.UUID,
        scoring_version: str,
        status: str,
        final_score: float | None = None,
        grade: str | None = None,
        confidence: float | None = None,
        deductions: list[Any] | None = None,
        caps: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> Score:
        score = Score(
            score_id=uuid.uuid4(),
            run_id=run_id,
            scoring_version=scoring_version,
            status=status,
            final_score=final_score,
            grade=grade,
            confidence=confidence,
            deductions=deductions or [],
            caps=caps or [],
            limitations=limitations or [],
            created_at=datetime.now(UTC),
        )
        self._session.add(score)
        await self._session.flush()
        return score

    async def get_by_run(self, run_id: uuid.UUID) -> Score | None:
        result = await self._session.execute(
            select(Score).where(Score.run_id == run_id)
        )
        return result.scalar_one_or_none()
