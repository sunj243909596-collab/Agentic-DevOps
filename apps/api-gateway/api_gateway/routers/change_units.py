from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from devmanager_db.models import ChangeUnit

router = APIRouter(prefix="/v1/change-units", tags=["change-units"])


@router.get("/{change_unit_id}/hunk", response_class=PlainTextResponse)
async def get_hunk(
    change_unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> str:
    result = await db.execute(
        select(ChangeUnit).where(ChangeUnit.change_unit_id == change_unit_id)
    )
    unit = result.scalar_one_or_none()
    if unit is None:
        raise HTTPException(status_code=404, detail=f"ChangeUnit {change_unit_id} not found")

    if not unit.hunks_ref:
        raise HTTPException(status_code=404, detail="No hunk available for this change unit")

    hunk_path = Path(unit.hunks_ref.removeprefix("file://"))
    if not hunk_path.exists():
        raise HTTPException(status_code=404, detail="Hunk file not found on disk")

    return hunk_path.read_text(encoding="utf-8", errors="replace")
