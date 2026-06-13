from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Setting


class SettingDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Setting]:
        result = await self._session.execute(select(Setting).order_by(Setting.key))
        return list(result.scalars().all())

    async def get(self, key: str) -> Setting | None:
        result = await self._session.execute(select(Setting).where(Setting.key == key))
        return result.scalar_one_or_none()

    async def get_value(self, key: str, default: str | None = None) -> str | None:
        s = await self.get(key)
        return s.value if s else default

    async def set_value(self, key: str, value: str, updated_by: str | None = None) -> Setting:
        existing = await self.get(key)
        now = datetime.now(UTC)
        if existing is None:
            s = Setting(key=key, value=value, updated_at=now, updated_by=updated_by)
            self._session.add(s)
        else:
            existing.value = value
            existing.updated_at = now
            existing.updated_by = updated_by
            s = existing
        await self._session.flush()
        return s

    async def set_many(self, items: dict[str, str], updated_by: str | None = None) -> list[Setting]:
        now = datetime.now(UTC)
        out: list[Setting] = []
        for k, v in items.items():
            existing = await self.get(k)
            if existing is None:
                s = Setting(key=k, value=v, updated_at=now, updated_by=updated_by)
                self._session.add(s)
            else:
                existing.value = v
                existing.updated_at = now
                existing.updated_by = updated_by
                s = existing
            out.append(s)
        await self._session.flush()
        return out
