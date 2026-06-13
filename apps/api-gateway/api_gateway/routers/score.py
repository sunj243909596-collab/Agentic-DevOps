from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from devmanager_scoring.service import AlreadyScoredError, ScoreError, score_run

router = APIRouter(prefix="/v1/analysis-runs", tags=["score"])


@router.post("/{run_id}/score", status_code=200)
async def trigger_score(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    try:
        score = await score_run(run_id, db)
    except AlreadyScoredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ScoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "run_id": str(run_id),
        "score_id": str(score.score_id),
        "final_score": float(score.final_score),
        "grade": score.grade,
        "confidence": float(score.confidence) if score.confidence is not None else None,
        "scoring_version": score.scoring_version,
        "caps": score.caps or [],
        "limitations": score.limitations or [],
    }
