from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Team


class TeamDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str, description: str | None = None) -> Team:
        now = datetime.now(UTC)
        team = Team(
            team_id=uuid.uuid4(),
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        self._session.add(team)
        await self._session.flush()
        return team

    async def get_by_id(self, team_id: uuid.UUID) -> Team | None:
        result = await self._session.execute(select(Team).where(Team.team_id == team_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Team | None:
        result = await self._session.execute(select(Team).where(Team.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Team]:
        result = await self._session.execute(select(Team).order_by(Team.name))
        return list(result.scalars().all())

    async def update(
        self,
        team_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        clear_description: bool = False,
    ) -> None:
        values: dict = {"updated_at": datetime.now(UTC)}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        elif clear_description:
            values["description"] = None
        if len(values) == 1:
            return
        await self._session.execute(sa_update(Team).where(Team.team_id == team_id).values(**values))

    async def delete(self, team_id: uuid.UUID) -> bool:
        result = await self._session.execute(sa_delete(Team).where(Team.team_id == team_id))
        return (result.rowcount or 0) > 0
