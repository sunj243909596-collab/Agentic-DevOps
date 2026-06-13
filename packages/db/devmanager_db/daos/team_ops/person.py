from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Person


class PersonDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        display_name: str,
        email: str,
        status: str = "active",
        data_access_scope: str = "self",
    ) -> Person:
        now = datetime.now(UTC)
        person = Person(
            person_id=uuid.uuid4(),
            display_name=display_name,
            email=email,
            status=status,
            data_access_scope=data_access_scope,
            created_at=now,
            updated_at=now,
        )
        self._session.add(person)
        await self._session.flush()
        return person

    async def get_by_id(self, person_id: uuid.UUID) -> Person | None:
        result = await self._session.execute(select(Person).where(Person.person_id == person_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Person | None:
        result = await self._session.execute(select(Person).where(Person.email == email))
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str) -> list[Person]:
        result = await self._session.execute(
            select(Person).where(Person.status == status).order_by(Person.display_name)
        )
        return list(result.scalars().all())

    async def list_active(self) -> list[Person]:
        """v1 便捷方法：列出全部 active person（S1/S2/S3 都会用）。"""
        return await self.list_by_status("active")

    async def list_all(self) -> list[Person]:
        result = await self._session.execute(select(Person).order_by(Person.display_name))
        return list(result.scalars().all())

    async def update(
        self,
        person_id: uuid.UUID,
        *,
        display_name: str | None = None,
        email: str | None = None,
        status: str | None = None,
        data_access_scope: str | None = None,
    ) -> None:
        values: dict = {"updated_at": datetime.now(UTC)}
        if display_name is not None:
            values["display_name"] = display_name
        if email is not None:
            values["email"] = email
        if status is not None:
            values["status"] = status
        if data_access_scope is not None:
            values["data_access_scope"] = data_access_scope
        if len(values) == 1:
            return
        await self._session.execute(
            sa_update(Person).where(Person.person_id == person_id).values(**values)
        )

    async def delete(self, person_id: uuid.UUID) -> bool:
        result = await self._session.execute(sa_delete(Person).where(Person.person_id == person_id))
        return (result.rowcount or 0) > 0
