from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db, require_auth
from devmanager_db.daos.report import ReportDAO
from devmanager_reporting.service import AlreadyReportedError, ReportError, generate_report

router = APIRouter(prefix="/v1/analysis-runs", tags=["report"])


@router.post("/{run_id}/report", status_code=200)
async def trigger_report(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> dict:
    try:
        report = await generate_report(run_id, db)
    except AlreadyReportedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ReportError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "run_id": str(run_id),
        "report_id": str(report.report_id),
        "content_reference": report.content_reference,
        "generated_at": report.generated_at.isoformat(),
    }


@router.get("/{run_id}/report/content", response_class=PlainTextResponse)
async def get_report_content(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _auth: str = Depends(require_auth),
) -> str:
    report_dao = ReportDAO(db)
    report = await report_dao.get_by_run(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for run {run_id}")

    ref = report.content_reference
    if ref.startswith("file://"):
        path = Path(ref.removeprefix("file://"))
        if not path.exists():
            raise HTTPException(status_code=404, detail="Report file not found on disk")
        return path.read_text(encoding="utf-8")

    raise HTTPException(status_code=501, detail="Non-file content_reference not supported")
