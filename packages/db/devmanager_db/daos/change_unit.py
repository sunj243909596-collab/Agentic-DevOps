from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.models import ChangeUnit


class ChangeUnitDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(self, units: list[dict]) -> list[ChangeUnit]:
        rows = []
        for u in units:
            row = ChangeUnit(
                change_unit_id=u.get("change_unit_id") or uuid.uuid4(),
                run_id=u["run_id"],
                repository_full_name=u["repository_full_name"],
                baseline_sha=u["baseline_sha"],
                target_sha=u["target_sha"],
                file_path=u["file_path"],
                previous_file_path=u.get("previous_file_path"),
                change_type=u["change_type"],
                language=u.get("language", "unknown"),
                owner=u.get("owner"),
                added_lines=u.get("added_lines", 0),
                deleted_lines=u.get("deleted_lines", 0),
                is_binary=u.get("is_binary", False),
                is_generated=u.get("is_generated", False),
                is_vendor=u.get("is_vendor", False),
                is_test_file=u.get("is_test_file", False),
                risk_tags=u.get("risk_tags", []),
                hunks_ref=u.get("hunks_ref"),
                created_at=datetime.now(UTC),
            )
            self._session.add(row)
            rows.append(row)
        await self._session.flush()
        return rows

    async def bulk_update_hunks_and_owners(
        self,
        updates: dict[str, dict],
    ) -> None:
        """
        updates: {change_unit_id_str: {"hunks_ref": str|None, "owner": str|None}}
        Only non-None values are written.
        """
        from sqlalchemy import update as sa_update

        for cu_id_str, vals in updates.items():
            cu_id = uuid.UUID(cu_id_str)
            set_vals = {k: v for k, v in vals.items() if v is not None}
            if not set_vals:
                continue
            await self._session.execute(
                sa_update(ChangeUnit).where(ChangeUnit.change_unit_id == cu_id).values(**set_vals)
            )

    async def list_by_run(self, run_id: uuid.UUID) -> list[ChangeUnit]:
        result = await self._session.execute(select(ChangeUnit).where(ChangeUnit.run_id == run_id))
        return list(result.scalars().all())
