from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Baseline


class BaselineDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, repository_id: uuid.UUID, branch: str) -> Baseline | None:
        result = await self._session.execute(
            select(Baseline).where(
                Baseline.repository_id == repository_id,
                Baseline.branch == branch,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        repository_id: uuid.UUID,
        branch: str,
        last_successful_sha: str,
        run_id: uuid.UUID | None = None,
    ) -> Baseline:
        """Insert or update the baseline for (repository_id, branch).

        Only called on successful analysis runs — never on failed/partial runs.
        """
        stmt = (
            insert(Baseline)
            .values(
                repository_id=repository_id,
                branch=branch,
                last_successful_sha=last_successful_sha,
                run_id=run_id,
                updated_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["repository_id", "branch"],
                set_={
                    "last_successful_sha": last_successful_sha,
                    "run_id": run_id,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(Baseline)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one()
