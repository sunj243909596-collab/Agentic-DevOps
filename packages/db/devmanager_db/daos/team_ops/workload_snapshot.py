"""S4 P4 — WorkloadSnapshotDAO。"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import WorkloadSnapshot


class WorkloadSnapshotDAO:
    """workload_snapshot 读写。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        person_id: uuid.UUID,
        time_window: str,
        open_issues: int,
        in_progress_issues: int,
        completed_issues: int,
        estimate_hours_remaining: float,
        estimate_hours_completed: float,
    ) -> None:
        """按 (person_id, time_window) 幂等 upsert，computed_at = now(UTC)。"""
        stmt = pg_insert(WorkloadSnapshot).values(
            person_id=person_id,
            time_window=time_window,
            open_issues=open_issues,
            in_progress_issues=in_progress_issues,
            completed_issues=completed_issues,
            estimate_hours_remaining=estimate_hours_remaining,
            estimate_hours_completed=estimate_hours_completed,
            computed_at=datetime.now(UTC),
        ).on_conflict_do_update(
            index_elements=["person_id", "time_window"],
            set_={
                "open_issues": open_issues,
                "in_progress_issues": in_progress_issues,
                "completed_issues": completed_issues,
                "estimate_hours_remaining": estimate_hours_remaining,
                "estimate_hours_completed": estimate_hours_completed,
                "computed_at": datetime.now(UTC),
            },
        )
        await self._session.execute(stmt)

    async def get(
        self, person_id: uuid.UUID, time_window: str,
    ) -> WorkloadSnapshot | None:
        result = await self._session.execute(
            select(WorkloadSnapshot).where(
                WorkloadSnapshot.person_id == person_id,
                WorkloadSnapshot.time_window == time_window,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_window(self, time_window: str) -> list[WorkloadSnapshot]:
        result = await self._session.execute(
            select(WorkloadSnapshot)
            .where(WorkloadSnapshot.time_window == time_window)
            .order_by(WorkloadSnapshot.estimate_hours_remaining.desc())
        )
        return list(result.scalars().all())
