"""
GitLab Webhook handler.

POST /v1/webhooks/gitlab

Validates the shared secret from ``X-Gitlab-Token`` (when
``GITLAB_WEBHOOK_SECRET`` is set), parses Push Hook and Merge Request Hook
events, creates a Repository + AnalysisRun, enqueues a background
``full_pipeline`` job via ARQ, returns 202 immediately.

GitLab event headers:
  • X-Gitlab-Event  (e.g. "Push Hook", "Merge Request Hook", "Tag Push Hook")
  • X-Gitlab-Token  (shared secret, plain comparison)

Events ignored (no run created, returns 202 with message):
  • tag push (ref not starting with refs/heads/)
  • branch deletion (after SHA is all-zeros)
  • MR actions other than open / update / reopen / merge
  • system hooks
"""

from __future__ import annotations

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


# ── Secret verification ───────────────────────────────────────────────────────


def _verify_token(token: str | None) -> None:
    """Raise HTTP 403 if the X-Gitlab-Token does not match the configured secret.

    Verification is skipped when GITLAB_WEBHOOK_SECRET is not configured,
    allowing local development without a shared secret.
    """
    secret = os.getenv("GITLAB_WEBHOOK_SECRET", "")
    if not secret:
        return
    if not token or token != secret:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Gitlab-Token")


# ── Event parsers ─────────────────────────────────────────────────────────────


def _parse_push(payload: dict) -> dict | None:
    """Return event data for an actionable branch push, or None to ignore.

    GitLab Push Hook payload:
      {
        "ref": "refs/heads/main",
        "before": "abc...",   # NULL_SHA on first push of new branch
        "after":  "def...",
        "project": { "path_with_namespace": "gywl/bar2-test",
                     "git_http_url":  "https://...",
                     "default_branch": "main" },
        "user_username": "alice"
      }
    """
    ref: str = payload.get("ref", "")
    if not ref.startswith("refs/heads/"):
        return None  # tag push
    branch = ref.removeprefix("refs/heads/")

    after: str = payload.get("after", _NULL_SHA)
    if after == _NULL_SHA:
        return None  # branch deletion

    before: str = payload.get("before", _NULL_SHA)
    project: dict = payload.get("project", {})

    return {
        "baseline_sha": before,
        "target_sha": after,
        "target_branch": branch,
        "clone_url": project.get("git_http_url") or project.get("http_url"),
        "repository_full_name": project.get("path_with_namespace", ""),
        "actor": payload.get("user_username") or payload.get("user_username"),
    }


def _parse_merge_request(payload: dict) -> dict | None:
    """Return event data for an actionable MR event, or None to ignore.

    GitLab Merge Request Hook payload:
      {
        "object_attributes": {
          "source_branch": "feature/x",
          "target_branch": "main",
          "action": "open" | "update" | "reopen" | "merge" | "close",
          "last_commit": { "id": "sha" }
        },
        "project": { "path_with_namespace": "...", "git_http_url": "..." }
      }
    """
    attrs: dict = payload.get("object_attributes", {})
    action: str = attrs.get("action", "")
    if action not in ("open", "update", "reopen", "merge"):
        return None

    project: dict = payload.get("project", {})

    # baseline = target branch tip at MR creation (we don't have the SHA directly;
    # we let the worker resolve merge-base against the local mirror, so use NULL_SHA
    # to force a full diff)
    last_commit: dict = attrs.get("last_commit") or {}
    target_sha: str = last_commit.get("id") or _NULL_SHA

    return {
        "baseline_sha": _NULL_SHA,  # worker will compute merge-base
        "target_sha": target_sha,
        "target_branch": attrs.get("source_branch", ""),
        "clone_url": project.get("git_http_url") or project.get("http_url"),
        "repository_full_name": project.get("path_with_namespace", ""),
        "actor": payload.get("user_username"),
    }


# ── Database helper ───────────────────────────────────────────────────────────


async def _create_run(
    db: AsyncSession,
    event_data: dict,
    trigger_type: str,
) -> AnalysisRun:
    """Get-or-create Repository (preserving stored PAT), then create AnalysisRun."""
    repo_dao = RepositoryDAO(db)
    run_dao = AnalysisRunDAO(db)

    full_name: str = event_data["repository_full_name"]
    clone_url: str | None = event_data.get("clone_url")

    repo = await repo_dao.get_by_full_name(full_name)
    if repo is None:
        repo = await repo_dao.create(
            provider="gitlab",
            full_name=full_name,
            clone_url=clone_url,
        )
    elif clone_url and not repo.clone_url:
        await repo_dao.update_clone_url(repo.repository_id, clone_url)
    # Note: access_token is NOT touched by webhooks. Configure via API or DB.

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


@router.post("/gitlab", status_code=202)
async def gitlab_webhook(
    request: Request,
    x_gitlab_event: str | None = Header(default=None, alias="X-Gitlab-Event"),
    x_gitlab_token: str | None = Header(default=None, alias="X-Gitlab-Token"),
    db: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> dict:
    """Receive a GitLab webhook, create an AnalysisRun, enqueue the pipeline."""
    body = await request.body()

    _verify_token(x_gitlab_token)

    # GitLab sends "ping" implicitly on hook creation; surface as 200/202
    if not x_gitlab_event:
        return {"message": "missing X-Gitlab-Event header"}

    if x_gitlab_event == "System Hook":
        return {"message": "system hooks not handled"}

    if x_gitlab_event == "Tag Push Hook":
        return {"message": "tag push ignored"}

    if x_gitlab_event not in ("Push Hook", "Merge Request Hook"):
        return {"message": f"event '{x_gitlab_event}' not handled"}

    import json

    payload: dict = json.loads(body)

    event_data: dict | None
    if x_gitlab_event == "Push Hook":
        event_data = _parse_push(payload)
    else:  # Merge Request Hook
        event_data = _parse_merge_request(payload)

    if event_data is None:
        return {"message": f"event '{x_gitlab_event}' ignored (not actionable)"}

    trigger_type = "push" if x_gitlab_event == "Push Hook" else "merge_request"
    run = await _create_run(db, event_data, trigger_type)
    run_id_str = str(run.run_id)

    if pool is not None:
        await pool.enqueue_job("full_pipeline", run_id_str)
        log.info("Enqueued full_pipeline for run=%s (gitlab event=%s)", run_id_str, x_gitlab_event)
    else:
        log.warning("ARQ pool unavailable — run=%s not enqueued", run_id_str)

    return {"run_id": run_id_str, "status": "queued", "event": x_gitlab_event}


@router.post("/gitlab/test", status_code=202)
async def gitlab_test_webhook(
    db: AsyncSession = Depends(get_db),
    pool=Depends(get_arq_pool),
) -> dict:
    """Simulate a GitLab Push Hook for end-to-end testing from the Webhooks page."""
    payload = {
        "ref": "refs/heads/main",
        "before": "0" * 40,
        "after": "a" * 40,
        "user_username": "test-user",
        "project": {
            "path_with_namespace": "test/webhook-smoke",
            "git_http_url": "https://gitlab.example.com/test/webhook-smoke.git",
        },
    }
    event_data = _parse_push(payload)
    if event_data is None:
        raise HTTPException(status_code=400, detail="test payload produced no event data")
    run = await _create_run(db, event_data, "push")
    run_id_str = str(run.run_id)
    if pool is not None:
        await pool.enqueue_job("full_pipeline", run_id_str)
    return {"run_id": run_id_str, "status": "queued (test event)"}
