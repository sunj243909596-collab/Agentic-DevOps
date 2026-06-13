from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Repository


class RepositoryDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        provider: str,
        full_name: str,
        clone_url: str | None = None,
        default_branch: str = "main",
        owner_team: str | None = None,
        policy_id: str = "default-readonly",
        status: str = "active",
    ) -> Repository:
        now = datetime.now(UTC)
        repo = Repository(
            repository_id=uuid.uuid4(),
            provider=provider,
            full_name=full_name,
            clone_url=clone_url,
            default_branch=default_branch,
            owner_team=owner_team,
            policy_id=policy_id,
            status=status,
            created_at=now,
            updated_at=now,
        )
        self._session.add(repo)
        await self._session.flush()
        return repo

    async def update_clone_url(self, repository_id: uuid.UUID, clone_url: str) -> None:
        from datetime import datetime

        from sqlalchemy import update as sa_update
        await self._session.execute(
            sa_update(Repository)
            .where(Repository.repository_id == repository_id)
            .values(clone_url=clone_url, updated_at=datetime.now(UTC))
        )

    async def update_access_token(
        self, repository_id: uuid.UUID, access_token: str | None
    ) -> None:
        from datetime import datetime

        from sqlalchemy import update as sa_update
        await self._session.execute(
            sa_update(Repository)
            .where(Repository.repository_id == repository_id)
            .values(access_token=access_token, updated_at=datetime.now(UTC))
        )

    async def update(
        self,
        repository_id: uuid.UUID,
        *,
        clone_url: str | None = None,
        clear_clone_url: bool = False,
        access_token: str | None = None,
        clear_access_token: bool = False,
        status: str | None = None,
        default_branch: str | None = None,
        provider: str | None = None,
    ) -> None:
        """Partial update. To explicitly CLEAR a nullable field, set the matching
        `clear_<field>` flag to True (don't pass None — that means "leave alone")."""
        from datetime import datetime

        from sqlalchemy import update as sa_update
        values: dict = { "updated_at": datetime.now(UTC) }
        if clone_url is not None:
            values["clone_url"] = clone_url
        elif clear_clone_url:
            values["clone_url"] = None
        if access_token is not None:
            values["access_token"] = access_token
        elif clear_access_token:
            values["access_token"] = None
        if status is not None:
            values["status"] = status
        if default_branch is not None:
            values["default_branch"] = default_branch
        if provider is not None:
            values["provider"] = provider
        if len(values) == 1:
            return  # nothing to update
        await self._session.execute(
            sa_update(Repository)
            .where(Repository.repository_id == repository_id)
            .values(**values)
        )

    async def delete(self, repository_id: uuid.UUID) -> bool:
        from sqlalchemy import delete as sa_delete
        result = await self._session.execute(
            sa_delete(Repository).where(Repository.repository_id == repository_id)
        )
        return (result.rowcount or 0) > 0

    async def get_by_id(self, repository_id: uuid.UUID) -> Repository | None:
        result = await self._session.execute(
            select(Repository).where(Repository.repository_id == repository_id)
        )
        return result.scalar_one_or_none()

    async def get_by_full_name(self, full_name: str) -> Repository | None:
        result = await self._session.execute(
            select(Repository).where(Repository.full_name == full_name)
        )
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Repository]:
        result = await self._session.execute(
            select(Repository).where(Repository.status == "active")
        )
        return list(result.scalars().all())
