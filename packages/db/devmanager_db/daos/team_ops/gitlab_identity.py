from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import GitlabIdentity


class GitlabIdentityDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def map(
        self,
        *,
        person_id: uuid.UUID,
        gitlab_user_id: int,
        gitlab_username: str,
        effective_from: datetime | None = None,
    ) -> GitlabIdentity:
        """Create a NEW identity row. The DB-level partial-unique-index will
        reject if another active row with the same gitlab_user_id exists."""
        ts = effective_from or datetime.now(UTC)
        row = GitlabIdentity(
            identity_id=uuid.uuid4(),
            person_id=person_id,
            gitlab_user_id=gitlab_user_id,
            gitlab_username=gitlab_username,
            effective_from=ts,
            effective_to=None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_active_by_user_id(
        self, gitlab_user_id: int
    ) -> GitlabIdentity | None:
        result = await self._session.execute(
            select(GitlabIdentity).where(
                GitlabIdentity.gitlab_user_id == gitlab_user_id,
                GitlabIdentity.effective_to.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_active_by_person(
        self, person_id: uuid.UUID
    ) -> list[GitlabIdentity]:
        result = await self._session.execute(
            select(GitlabIdentity)
            .where(
                GitlabIdentity.person_id == person_id,
                GitlabIdentity.effective_to.is_(None),
            )
            .order_by(GitlabIdentity.effective_from.desc())
        )
        return list(result.scalars().all())

    async def list_history_by_person(
        self, person_id: uuid.UUID
    ) -> list[GitlabIdentity]:
        """All rows (active + deactivated) for audit history."""
        result = await self._session.execute(
            select(GitlabIdentity)
            .where(GitlabIdentity.person_id == person_id)
            .order_by(GitlabIdentity.effective_from.desc())
        )
        return list(result.scalars().all())

    async def deactivate(
        self,
        identity_id: uuid.UUID,
        *,
        effective_to: datetime | None = None,
    ) -> bool:
        """Soft-deactivate: set effective_to = now (or specified ts). Returns
        True if a row was updated."""
        from sqlalchemy import update as sa_update

        ts = effective_to or datetime.now(UTC)
        result = await self._session.execute(
            sa_update(GitlabIdentity)
            .where(
                GitlabIdentity.identity_id == identity_id,
                GitlabIdentity.effective_to.is_(None),
            )
            .values(effective_to=ts)
        )
        return (result.rowcount or 0) > 0
