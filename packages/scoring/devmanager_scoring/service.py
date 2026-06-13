from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.audit_event import AuditEventDAO
from devmanager_db.daos.finding import FindingDAO
from devmanager_db.daos.score import ScoreDAO
from devmanager_db.models import Score
from devmanager_scoring.engine import compute_score

_SCORING_VERSION = os.getenv("SCORING_VERSION", "v1")

log = logging.getLogger(__name__)


class ScoreError(Exception):
    pass


class AlreadyScoredError(ScoreError):
    pass


async def score_run(run_id: uuid.UUID, db: AsyncSession) -> Score:
    """
    Load findings for the run, compute a deterministic score, persist it,
    and advance the run status to "scored".

    Raises:
        ScoreError:        run not found.
        AlreadyScoredError: score already exists for this run (idempotent guard).
    """
    run_dao = AnalysisRunDAO(db)
    run = await run_dao.get_by_id(run_id)
    if run is None:
        raise ScoreError(f"AnalysisRun {run_id} not found")

    score_dao = ScoreDAO(db)
    existing = await score_dao.get_by_run(run_id)
    if existing is not None:
        raise AlreadyScoredError(f"Run {run_id} already scored (score_id={existing.score_id})")

    finding_dao = FindingDAO(db)
    findings = await finding_dao.list_by_run(run_id)

    result = compute_score(findings)

    score = await score_dao.create(
        run_id=run_id,
        scoring_version=_SCORING_VERSION,
        status="complete",
        **result.as_db_kwargs(),
    )

    await run_dao.update_status(run_id, "scored")

    audit_dao = AuditEventDAO(db)
    try:
        await audit_dao.append(
            actor="system",
            workflow_id=run_id,
            event_type="run.scored",
            event_timestamp=datetime.now(timezone.utc),
            metadata={
                "score_id": str(score.score_id),
                "final_score": result.final_score,
                "grade": result.grade,
                "findings_count": len(findings),
            },
        )
    except Exception as exc:
        log.warning("Failed to emit audit event for scoring %s: %s", run_id, exc)

    await db.commit()
    return score
