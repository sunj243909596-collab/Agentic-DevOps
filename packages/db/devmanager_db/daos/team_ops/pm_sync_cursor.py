"""S4 P3 — PmSyncCursorDAO。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import PmSyncCursor


class PmSyncCursorDAO:
    """PM 平台增量同步水位线读写。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, source_key: str) -> PmSyncCursor | None:
        result = await self._session.execute(
            select(PmSyncCursor).where(PmSyncCursor.source_key == source_key)
        )
        return result.scalar_one_or_none()

    async def upsert(self, source_key: str, cursor_value: str | None) -> PmSyncCursor:
        """写入 / 更新水位线。last_synced_at 强制 = now(UTC)。"""
        existing = await self.get(source_key)
        if existing is None:
            row = PmSyncCursor(
                source_key=source_key,
                cursor_value=cursor_value,
                last_synced_at=datetime.now(UTC),
            )
            self._session.add(row)
        else:
            existing.cursor_value = cursor_value
            existing.last_synced_at = datetime.now(UTC)
            row = existing
        await self._session.flush()
        return row
