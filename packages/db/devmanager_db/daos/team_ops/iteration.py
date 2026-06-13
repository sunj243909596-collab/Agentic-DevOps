from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Iteration


class IterationDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_from_pm(
        self,
        *,
        pm_iteration_id: str,
        name: str,
        start_date: datetime,
        end_date: datetime,
        status: str,
        pm_created_at: datetime | None = None,
        pm_updated_at: datetime | None = None,
    ) -> Iteration:
        """Upsert by pm_iteration_id. last_synced_at 永远 = now()."""
        now = datetime.now(UTC)
        existing = await self.get_by_pm_id(pm_iteration_id)
        if existing is not None:
            await self._session.execute(
                sa_update(Iteration)
                .where(Iteration.iteration_id == existing.iteration_id)
                .values(
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    status=status,
                    pm_created_at=pm_created_at,
                    pm_updated_at=pm_updated_at,
                    last_synced_at=now,
                )
            )
            await self._session.flush()
            return existing
        row = Iteration(
            iteration_id=uuid.uuid4(),
            pm_iteration_id=pm_iteration_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            status=status,
            pm_created_at=pm_created_at,
            pm_updated_at=pm_updated_at,
            last_synced_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_id(self, iteration_id: uuid.UUID) -> Iteration | None:
        result = await self._session.execute(
            select(Iteration).where(Iteration.iteration_id == iteration_id)
        )
        return result.scalar_one_or_none()

    async def get_by_pm_id(self, pm_iteration_id: str) -> Iteration | None:
        result = await self._session.execute(
            select(Iteration).where(Iteration.pm_iteration_id == pm_iteration_id)
        )
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str) -> list[Iteration]:
        result = await self._session.execute(
            select(Iteration).where(Iteration.status == status).order_by(Iteration.start_date)
        )
        return list(result.scalars().all())

    async def list_active(self) -> list[Iteration]:
        result = await self._session.execute(
            select(Iteration)
            .where(Iteration.status.in_(("planning", "active")))
            .order_by(Iteration.start_date)
        )
        return list(result.scalars().all())
