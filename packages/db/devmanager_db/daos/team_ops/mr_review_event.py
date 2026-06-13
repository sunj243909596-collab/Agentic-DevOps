from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import MrReviewEvent


class MrReviewEventDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        project_id: int,
        mr_iid: int,
        action: str,
        event_created_at: datetime,
        author_gitlab_user_id: int | None = None,
        author_pm_user_id: str | None = None,
        target_sha: str | None = None,
        source_branch: str | None = None,
        target_branch: str | None = None,
        title: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> MrReviewEvent | None:
        """幂等写入。命中唯一约束 (project_id, mr_iid, action, event_created_at) 时返回 None。"""
        row = MrReviewEvent(
            event_id=uuid.uuid4(),
            project_id=project_id,
            mr_iid=mr_iid,
            action=action,
            author_gitlab_user_id=author_gitlab_user_id,
            author_pm_user_id=author_pm_user_id,
            target_sha=target_sha,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            event_created_at=event_created_at,
            raw_payload=raw_payload or {},
            ingested_at=datetime.now(UTC),
        )
        self._session.add(row)
        try:
            await self._session.flush()
            return row
        except IntegrityError:
            # 幂等：同一 (project, mr, action, time) 已存在
            await self._session.rollback()
            return None

    async def list_by_project(self, project_id: int, *, limit: int = 100) -> list[MrReviewEvent]:
        result = await self._session.execute(
            select(MrReviewEvent)
            .where(MrReviewEvent.project_id == project_id)
            .order_by(MrReviewEvent.event_created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_author_gitlab(
        self, gitlab_user_id: int, *, limit: int = 100
    ) -> list[MrReviewEvent]:
        result = await self._session.execute(
            select(MrReviewEvent)
            .where(MrReviewEvent.author_gitlab_user_id == gitlab_user_id)
            .order_by(MrReviewEvent.event_created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
