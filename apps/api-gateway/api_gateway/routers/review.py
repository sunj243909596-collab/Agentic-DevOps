from __future__ import annotations

import os
import uuid

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from devmanager_agents.service import ReviewError, review_run

router = APIRouter(prefix="/v1/analysis-runs", tags=["review"])


@router.post("/{run_id}/review", status_code=202)
async def trigger_review(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    # ANTHROPIC_AUTH_TOKEN takes priority (DeepSeek / proxy), falls back to ANTHROPIC_API_KEY
    api_key = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY not configured",
        )

    base_url = os.getenv("ANTHROPIC_BASE_URL") or None  # None → SDK uses official endpoint
    client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)
    try:
        findings = await review_run(run_id, db, client)
    except ReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "run_id": str(run_id),
        "findings_count": len(findings),
        "finding_ids": [f.finding_id for f in findings],
    }
