from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import TeamMembership


class TeamMembershipDAO:
    """junction DAO — PK is (team_id, person_id) so no get_by_id()."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        team_id: uuid.UUID,
        person_id: uuid.UUID,
        role: str = "member",
    ) -> TeamMembership:
        now = datetime.now(UTC)
        m = TeamMembership(
            team_id=team_id,
            person_id=person_id,
            role=role,
            joined_at=now,
            left_at=None,
        )
        self._session.add(m)
        await self._session.flush()
        return m

    async def get(self, team_id: uuid.UUID, person_id: uuid.UUID) -> TeamMembership | None:
        result = await self._session.execute(
            select(TeamMembership).where(
                TeamMembership.team_id == team_id,
                TeamMembership.person_id == person_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_team(
        self, team_id: uuid.UUID, *, active_only: bool = False
    ) -> list[TeamMembership]:
        stmt = select(TeamMembership).where(TeamMembership.team_id == team_id)
        if active_only:
            stmt = stmt.where(TeamMembership.left_at.is_(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_person(
        self, person_id: uuid.UUID, *, active_only: bool = False
    ) -> list[TeamMembership]:
        stmt = select(TeamMembership).where(TeamMembership.person_id == person_id)
        if active_only:
            stmt = stmt.where(TeamMembership.left_at.is_(None))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_role(self, team_id: uuid.UUID, person_id: uuid.UUID, *, role: str) -> None:
        await self._session.execute(
            sa_update(TeamMembership)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.person_id == person_id,
            )
            .values(role=role)
        )

    async def mark_left(
        self,
        team_id: uuid.UUID,
        person_id: uuid.UUID,
        *,
        left_at: datetime | None = None,
    ) -> None:
        ts = left_at or datetime.now(UTC)
        await self._session.execute(
            sa_update(TeamMembership)
            .where(
                TeamMembership.team_id == team_id,
                TeamMembership.person_id == person_id,
            )
            .values(left_at=ts)
        )

    async def remove(self, team_id: uuid.UUID, person_id: uuid.UUID) -> bool:
        """Hard delete. Prefer `mark_left` for soft-leave semantics."""
        result = await self._session.execute(
            sa_delete(TeamMembership).where(
                TeamMembership.team_id == team_id,
                TeamMembership.person_id == person_id,
            )
        )
        return (result.rowcount or 0) > 0
