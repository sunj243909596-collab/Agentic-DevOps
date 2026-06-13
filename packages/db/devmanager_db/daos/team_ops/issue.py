from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Issue


class IssueDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_from_pm(
        self,
        *,
        pm_issue_id: str,
        issue_key: str,
        title: str,
        issue_type: str,
        priority: str,
        status: str,
        estimate_hours: float | None = None,
        iteration_id: uuid.UUID | None = None,
        pm_created_at: datetime | None = None,
        pm_updated_at: datetime | None = None,
    ) -> Issue:
        now = datetime.now(UTC)
        existing = await self.get_by_pm_id(pm_issue_id)
        if existing is not None:
            await self._session.execute(
                sa_update(Issue)
                .where(Issue.issue_id == existing.issue_id)
                .values(
                    issue_key=issue_key,
                    title=title,
                    issue_type=issue_type,
                    priority=priority,
                    status=status,
                    estimate_hours=estimate_hours,
                    iteration_id=iteration_id,
                    pm_created_at=pm_created_at,
                    pm_updated_at=pm_updated_at,
                    last_synced_at=now,
                )
            )
            await self._session.flush()
            return existing
        row = Issue(
            issue_id=uuid.uuid4(),
            pm_issue_id=pm_issue_id,
            issue_key=issue_key,
            title=title,
            issue_type=issue_type,
            priority=priority,
            status=status,
            estimate_hours=estimate_hours,
            iteration_id=iteration_id,
            pm_created_at=pm_created_at,
            pm_updated_at=pm_updated_at,
            last_synced_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_id(self, issue_id: uuid.UUID) -> Issue | None:
        result = await self._session.execute(
            select(Issue).where(Issue.issue_id == issue_id)
        )
        return result.scalar_one_or_none()

    async def get_by_pm_id(self, pm_issue_id: str) -> Issue | None:
        result = await self._session.execute(
            select(Issue).where(Issue.pm_issue_id == pm_issue_id)
        )
        return result.scalar_one_or_none()

    async def get_by_issue_key(self, issue_key: str) -> Issue | None:
        result = await self._session.execute(
            select(Issue).where(Issue.issue_key == issue_key)
        )
        return result.scalar_one_or_none()

    async def list_by_iteration(
        self, iteration_id: uuid.UUID, *, status: str | None = None
    ) -> list[Issue]:
        stmt = select(Issue).where(Issue.iteration_id == iteration_id)
        if status is not None:
            stmt = stmt.where(Issue.status == status)
        result = await self._session.execute(stmt.order_by(Issue.priority, Issue.issue_key))
        return list(result.scalars().all())

    async def list_by_status(self, status: str) -> list[Issue]:
        result = await self._session.execute(
            select(Issue).where(Issue.status == status).order_by(Issue.pm_updated_at)
        )
        return list(result.scalars().all())

    async def list_updated_since(self, since: datetime) -> list[Issue]:
        """增量同步用。"""
        result = await self._session.execute(
            select(Issue).where(Issue.pm_updated_at > since).order_by(Issue.pm_updated_at)
        )
        return list(result.scalars().all())
