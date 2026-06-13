from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Report


class ReportDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        run_id: uuid.UUID,
        report_type: str = "daily_markdown",
        status: str = "generated",
        content_reference: str,
        generated_at: datetime | None = None,
    ) -> Report:
        report = Report(
            report_id=uuid.uuid4(),
            run_id=run_id,
            report_type=report_type,
            status=status,
            content_reference=content_reference,
            generated_at=generated_at or datetime.now(UTC),
        )
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_by_run(self, run_id: uuid.UUID) -> Report | None:
        result = await self._session.execute(
            select(Report).where(Report.run_id == run_id)
        )
        return result.scalar_one_or_none()
