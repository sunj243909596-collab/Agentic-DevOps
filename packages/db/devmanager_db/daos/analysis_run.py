from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import AnalysisRun


class AnalysisRunDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        repository_id: uuid.UUID,
        repository_full_name: str,
        trigger_type: str,
        target_branch: str,
        baseline_sha: str,
        target_sha: str,
        status: str,
        policy_version: str,
        scoring_version: str,
        trigger_id: uuid.UUID | None = None,
        merge_base_sha: str | None = None,
        history_rewrite_detected: bool = False,
        agent_versions: dict | None = None,
    ) -> AnalysisRun:
        run = AnalysisRun(
            run_id=uuid.uuid4(),
            repository_id=repository_id,
            repository_full_name=repository_full_name,
            trigger_id=trigger_id,
            trigger_type=trigger_type,
            target_branch=target_branch,
            baseline_sha=baseline_sha,
            target_sha=target_sha,
            merge_base_sha=merge_base_sha,
            history_rewrite_detected=history_rewrite_detected,
            status=status,
            policy_version=policy_version,
            scoring_version=scoring_version,
            agent_versions=agent_versions or {},
            started_at=datetime.now(UTC),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> AnalysisRun | None:
        result = await self._session.execute(
            select(AnalysisRun).where(AnalysisRun.run_id == run_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        failure_reason: str | None = None,
    ) -> AnalysisRun | None:
        run = await self.get_by_id(run_id)
        if run is None:
            return None
        run.status = status
        if failure_reason is not None:
            run.failure_reason = failure_reason
        if status in ("completed", "partial_analysis", "failed", "rejected"):
            run.completed_at = datetime.now(UTC)
        await self._session.flush()
        return run

    async def list_by_repository(
        self,
        repository_id: uuid.UUID,
        limit: int = 20,
    ) -> list[AnalysisRun]:
        result = await self._session.execute(
            select(AnalysisRun)
            .where(AnalysisRun.repository_id == repository_id)
            .order_by(AnalysisRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_recent(self, limit: int = 50, offset: int = 0) -> list[AnalysisRun]:
        result = await self._session.execute(
            select(AnalysisRun)
            .order_by(AnalysisRun.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
