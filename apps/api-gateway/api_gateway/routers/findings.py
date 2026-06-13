from __future__ import annotations

from devmanager_db.daos.finding import FindingDAO
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from api_gateway.schemas.models import FindingResponse, FindingStatusUpdateIn

router = APIRouter(prefix="/v1/findings", tags=["findings"])


@router.patch("/{finding_id}/status", response_model=FindingResponse)
async def update_finding_status(
    finding_id: str,
    body: FindingStatusUpdateIn,
    db: AsyncSession = Depends(get_db),
    auth: str = Depends(require_auth),
) -> FindingResponse:
    finding = await FindingDAO(db).update_status(
        finding_id=finding_id,
        new_status=body.status,
        reason=body.reason,
        changed_by=auth if auth != "anonymous" else "api-user",
    )
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")
    await db.commit()
    return FindingResponse.model_validate(finding)
