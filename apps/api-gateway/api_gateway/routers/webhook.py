"""
GitHub Webhook handler.

POST /v1/webhooks/github

Validates the HMAC-SHA256 signature from X-Hub-Signature-256 (when
GITHUB_WEBHOOK_SECRET is set), parses push / pull_request events, creates
a Repository + AnalysisRun in the database, enqueues a background
``full_pipeline`` job via ARQ, and returns 202 immediately.

Events ignored (no run created, returns 202 with message):
  • push to a tag (ref not starting with refs/heads/)
  • branch deletion (after SHA is all-zeros)
  • pull_request actions other than opened / synchronize / reopened
  • any event type not in {push, pull_request}
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.repository import RepositoryDAO
from devmanager_db.models import AnalysisRun
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.dependencies import get_db
from api_gateway.queue import get_arq_pool

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

_NULL_SHA = "0" * 40
_POLICY_VERSION = os.getenv("POLICY_VERSION", "v1")
_SCORING_VERSION = os.getenv("SCORING_VERSION", "v1")


# ── Signature verification ────────────────────────────────────────────────────


def _verify_signature(body: bytes, signature: str | None) -> None:
    """Raise HTTP 403 if the HMAC signature is invalid or missing.

    Verification is skipped when GITHUB_WEBHOOK_SECRET is not configured,
    allowing local development without a shared secret.
    """
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        return  # no secret configured — skip verification
    if signature is None:
        raise HTTPException(status_code=403, detail="Missing X-Hub-Signature-256 header")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")


# ── Event parsers ─────────────────────────────────────────────────────────────


def _parse_push(payload: dict) -> dict | None:
    """Return event data dict for a branch push, or None if the event is not actionable."""
    ref: str = payload.get("ref", "")
    if not ref.startswith("refs/heads/"):
        return None  # tag push — not handled
    branch = ref.removeprefix("refs/heads/")
    after: str = payload.get("after", _NULL_SHA)
    if after == _NULL_SHA:
        return None  # branch deletion — not handled
    before: str = payload.get("before", _NULL_SHA)
    repo: dict = payload.get("repository", {})
    return {
        "baseline_sha": before,
        "target_sha": after,
        "target_branch": branch,
        "clone_url": repo.get("clone_url") or repo.get("ssh_url"),
        "repository_full_name": repo.get("full_name", ""),
        "actor": (payload.get("pusher") or {}).get("name"),
    }


def _parse_pull_request(payload: dict) -> dict | None:
    """Return event data dict for an actionable PR event, or None to ignore."""
    action: str = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return None
    pr: dict = payload.get("pull_request", {})
    repo: dict = payload.get("repository", {})
    return {
        "baseline_sha": (pr.get("base") or {}).get("sha", _NULL_SHA),
        "target_sha": (pr.get("head") or {}).get("sha", _NULL_SHA),
        "target_branch": (pr.get("head") or {}).get("ref", ""),
        "clone_url": repo.get("clone_url") or repo.get("ssh_url"),
        "repository_full_name": repo.get("full_name", ""),
        "actor": (pr.get("user") or {}).get("login"),
    }


# ── Database helpers ──────────────────────────────────────────────────────────


async def _create_run(
    db: AsyncSession,
    event_data: dict,
    trigger_type: str,
) -> AnalysisRun:
    """Get or create the Repository, then create and return an AnalysisRun."""
    repo_dao = RepositoryDAO(db)
    run_dao = AnalysisRunDAO(db)

    full_name: str = event_data["repository_full_name"]
    clone_url: str | None = event_data.get("clone_url")

    repo = await repo_dao.get_by_full_name(full_name)
    if repo is None:
        repo = await repo_dao.create(
            provider="github",
            full_name=full_name,
            clone_url=clone_url,
        )
    elif clone_url and not repo.clone_url:
        await repo_dao.update_clone_url(repo.repository_id, clone_url)

    run = await run_dao.create(
        repository_id=repo.repository_id,
        repository_full_name=repo.full_name,
        trigger_type=trigger_type,
        target_branch=event_data["target_branch"],
        baseline_sha=event_data["baseline_sha"],
        target_sha=event_data["target_sha"],
        status="trigger_received",
        policy_version=_POLICY_VERSION,
        scoring_version=_SCORING_VERSION,
    )
    await db.commit()
    return run


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> dict:
    """Receive a GitHub webhook, create an AnalysisRun, enqueue the pipeline."""
    body = await request.body()

    _verify_signature(body, x_hub_signature_256)

    if x_github_event == "ping":
        return {"message": "pong"}

    if x_github_event not in ("push", "pull_request"):
        return {"message": f"event '{x_github_event}' not handled"}

    payload: dict = json.loads(body)

    event_data: dict | None
    if x_github_event == "push":
        event_data = _parse_push(payload)
    else:
        event_data = _parse_pull_request(payload)

    if event_data is None:
        return {"message": f"event '{x_github_event}' ignored (not actionable)"}

    run = await _create_run(db, event_data, x_github_event)
    run_id_str = str(run.run_id)

    if pool is not None:
        await pool.enqueue_job("full_pipeline", run_id_str)
        log.info("Enqueued full_pipeline for run=%s", run_id_str)
    else:
        log.warning("ARQ pool unavailable — run=%s not enqueued", run_id_str)

    return {"run_id": run_id_str, "status": "queued"}
