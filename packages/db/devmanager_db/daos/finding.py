from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import Finding, FindingStatusHistory


class FindingDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, run_id: uuid.UUID, data: dict[str, Any]) -> Finding:
        now = datetime.now(UTC)
        finding = Finding(
            finding_pk=uuid.uuid4(),
            finding_id=data["finding_id"],
            run_id=run_id,
            category=data["category"],
            severity=data["severity"],
            confidence=data["confidence"],
            repository_full_name=data["repository"],
            commit_sha=data["commit_sha"],
            file_path=data["file"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            observation=data["observation"],
            impact=data["impact"],
            recommendation=data["recommendation"],
            verification=data["verification"],
            evidence_refs=data["evidence_refs"],
            related_knowledge_refs=data.get("related_knowledge_refs", []),
            status=data.get("status", "open"),
            dedupe_key=data.get("dedupe_key"),
            raw_agent_output=data.get("raw_agent_output", {}),
            created_at=now,
            updated_at=now,
        )
        self._session.add(finding)
        await self._session.flush()
        return finding

    async def get_by_id(self, finding_id: str) -> Finding | None:
        result = await self._session.execute(
            select(Finding).where(Finding.finding_id == finding_id)
        )
        return result.scalar_one_or_none()

    async def list_by_run(
        self,
        run_id: uuid.UUID,
        severity: str | None = None,
        status: str | None = None,
    ) -> list[Finding]:
        stmt = select(Finding).where(Finding.run_id == run_id)
        if severity:
            stmt = stmt.where(Finding.severity == severity)
        if status:
            stmt = stmt.where(Finding.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        finding_id: str,
        new_status: str,
        reason: str,
        changed_by: str,
    ) -> Finding | None:
        finding = await self.get_by_id(finding_id)
        if finding is None:
            return None
        history = FindingStatusHistory(
            history_id=uuid.uuid4(),
            finding_pk=finding.finding_pk,
            previous_status=finding.status,
            new_status=new_status,
            reason=reason,
            changed_by=changed_by,
            changed_at=datetime.now(UTC),
        )
        finding.status = new_status
        finding.updated_at = datetime.now(UTC)
        self._session.add(history)
        await self._session.flush()
        return finding
