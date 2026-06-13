"""S4 P4 — CapacitySnapshotDAO。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import CapacitySnapshot


class CapacitySnapshotDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        person_id: uuid.UUID,
        iteration_id: uuid.UUID,
        estimated_hours: float,
        weekly_capacity_hours: float,
        iteration_weeks: int,
    ) -> None:
        load_ratio = (
            estimated_hours / (weekly_capacity_hours * iteration_weeks)
            if weekly_capacity_hours > 0 and iteration_weeks > 0
            else 0.0
        )
        stmt = pg_insert(CapacitySnapshot).values(
            person_id=person_id,
            iteration_id=iteration_id,
            estimated_hours=estimated_hours,
            weekly_capacity_hours=weekly_capacity_hours,
            iteration_weeks=iteration_weeks,
            load_ratio=load_ratio,
            computed_at=datetime.now(UTC),
        ).on_conflict_do_update(
            index_elements=["person_id", "iteration_id"],
            set_={
                "estimated_hours": estimated_hours,
                "weekly_capacity_hours": weekly_capacity_hours,
                "iteration_weeks": iteration_weeks,
                "load_ratio": load_ratio,
                "computed_at": datetime.now(UTC),
            },
        )
        await self._session.execute(stmt)

    async def get(
        self, person_id: uuid.UUID, iteration_id: uuid.UUID,
    ) -> CapacitySnapshot | None:
        result = await self._session.execute(
            select(CapacitySnapshot).where(
                CapacitySnapshot.person_id == person_id,
                CapacitySnapshot.iteration_id == iteration_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_iteration(
        self, iteration_id: uuid.UUID,
    ) -> list[CapacitySnapshot]:
        result = await self._session.execute(
            select(CapacitySnapshot)
            .where(CapacitySnapshot.iteration_id == iteration_id)
            .order_by(CapacitySnapshot.load_ratio.desc())
        )
        return list(result.scalars().all())
