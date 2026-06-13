from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import PmIdentity


class PmIdentityDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def map(
        self,
        *,
        person_id: uuid.UUID,
        pm_user_id: str,
        pm_username: str,
        effective_from: datetime | None = None,
    ) -> PmIdentity:
        ts = effective_from or datetime.now(UTC)
        row = PmIdentity(
            identity_id=uuid.uuid4(),
            person_id=person_id,
            pm_user_id=pm_user_id,
            pm_username=pm_username,
            effective_from=ts,
            effective_to=None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_active_by_user_id(self, pm_user_id: str) -> PmIdentity | None:
        result = await self._session.execute(
            select(PmIdentity).where(
                PmIdentity.pm_user_id == pm_user_id,
                PmIdentity.effective_to.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_active_by_person(self, person_id: uuid.UUID) -> list[PmIdentity]:
        result = await self._session.execute(
            select(PmIdentity)
            .where(
                PmIdentity.person_id == person_id,
                PmIdentity.effective_to.is_(None),
            )
            .order_by(PmIdentity.effective_from.desc())
        )
        return list(result.scalars().all())

    async def list_history_by_person(self, person_id: uuid.UUID) -> list[PmIdentity]:
        result = await self._session.execute(
            select(PmIdentity)
            .where(PmIdentity.person_id == person_id)
            .order_by(PmIdentity.effective_from.desc())
        )
        return list(result.scalars().all())

    async def deactivate(
        self,
        identity_id: uuid.UUID,
        *,
        effective_to: datetime | None = None,
    ) -> bool:
        from sqlalchemy import update as sa_update

        ts = effective_to or datetime.now(UTC)
        result = await self._session.execute(
            sa_update(PmIdentity)
            .where(
                PmIdentity.identity_id == identity_id,
                PmIdentity.effective_to.is_(None),
            )
            .values(effective_to=ts)
        )
        return (result.rowcount or 0) > 0
