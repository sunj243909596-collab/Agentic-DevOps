from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import IssueAssignment


class IssueAssignmentDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_from_pm(
        self,
        *,
        issue_id: uuid.UUID,
        pm_user_id: str,
        pm_username: str,
        role: str,
        weight: float = 1.0,
        person_id: uuid.UUID | None = None,
    ) -> IssueAssignment:
        """Upsert by (issue_id, pm_user_id, role)."""
        now = datetime.now(UTC)
        existing = await self._session.execute(
            select(IssueAssignment).where(
                IssueAssignment.issue_id == issue_id,
                IssueAssignment.pm_user_id == pm_user_id,
                IssueAssignment.role == role,
            )
        )
        existing_row = existing.scalar_one_or_none()
        if existing_row is not None:
            await self._session.execute(
                sa_update(IssueAssignment)
                .where(IssueAssignment.assignment_id == existing_row.assignment_id)
                .values(
                    pm_username=pm_username,
                    weight=weight,
                    person_id=person_id,
                    last_synced_at=now,
                )
            )
            await self._session.flush()
            return existing_row
        row = IssueAssignment(
            assignment_id=uuid.uuid4(),
            issue_id=issue_id,
            person_id=person_id,
            pm_user_id=pm_user_id,
            pm_username=pm_username,
            role=role,
            weight=weight,
            last_synced_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_issue(self, issue_id: uuid.UUID) -> list[IssueAssignment]:
        result = await self._session.execute(
            select(IssueAssignment)
            .where(IssueAssignment.issue_id == issue_id)
            .order_by(IssueAssignment.role, IssueAssignment.pm_user_id)
        )
        return list(result.scalars().all())

    async def list_by_person(
        self, person_id: uuid.UUID, *, role: str | None = None
    ) -> list[IssueAssignment]:
        stmt = select(IssueAssignment).where(IssueAssignment.person_id == person_id)
        if role is not None:
            stmt = stmt.where(IssueAssignment.role == role)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def link_to_person(
        self, assignment_id: uuid.UUID, person_id: uuid.UUID
    ) -> None:
        """Identity CLI 写入时调用：把已知的 person 关联到 assignment。"""
        await self._session.execute(
            sa_update(IssueAssignment)
            .where(IssueAssignment.assignment_id == assignment_id)
            .values(person_id=person_id)
        )

    async def delete(self, assignment_id: uuid.UUID) -> bool:
        from sqlalchemy import delete as sa_delete

        result = await self._session.execute(
            sa_delete(IssueAssignment).where(IssueAssignment.assignment_id == assignment_id)
        )
        return (result.rowcount or 0) > 0
