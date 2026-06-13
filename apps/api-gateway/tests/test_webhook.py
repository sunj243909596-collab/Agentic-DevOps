"""
Tests for api_gateway/routers/webhook.py.

Unit-level: tests for helper functions (signature verification, event parsing).
Integration-level: tests for the full webhook endpoint via AsyncClient,
with all DB / ARQ dependencies overridden.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api_gateway.routers.webhook import (
    _parse_pull_request,
    _parse_push,
    _verify_signature,
)
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _push_payload(
    ref: str = "refs/heads/main",
    before: str = "a" * 40,
    after: str = "b" * 40,
    full_name: str = "org/repo",
    clone_url: str = "https://github.com/org/repo.git",
) -> dict:
    return {
        "ref": ref,
        "before": before,
        "after": after,
        "pusher": {"name": "alice"},
        "repository": {
            "full_name": full_name,
            "clone_url": clone_url,
        },
    }


def _pr_payload(
    action: str = "opened",
    base_sha: str = "a" * 40,
    head_sha: str = "b" * 40,
    head_ref: str = "feature/x",
    full_name: str = "org/repo",
    clone_url: str = "https://github.com/org/repo.git",
) -> dict:
    return {
        "action": action,
        "pull_request": {
            "base": {"sha": base_sha},
            "head": {"sha": head_sha, "ref": head_ref},
            "user": {"login": "bob"},
            "number": 42,
        },
        "repository": {
            "full_name": full_name,
            "clone_url": clone_url,
        },
    }


# ── _verify_signature unit tests ──────────────────────────────────────────────


def test_verify_signature_valid(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "mysecret")
    body = b'{"test": true}'
    sig = _sign("mysecret", body)
    _verify_signature(body, sig)  # should not raise


def test_verify_signature_invalid_raises_403(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "mysecret")
    body = b'{"test": true}'
    with pytest.raises(HTTPException) as exc_info:
        _verify_signature(body, "sha256=badhash")
    assert exc_info.value.status_code == 403


def test_verify_signature_missing_raises_403_when_secret_set(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "mysecret")
    body = b'{"test": true}'
    with pytest.raises(HTTPException) as exc_info:
        _verify_signature(body, None)
    assert exc_info.value.status_code == 403


def test_verify_signature_no_secret_skips(monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
    body = b'{"test": true}'
    _verify_signature(body, None)  # should not raise — no secret configured


# ── _parse_push unit tests ────────────────────────────────────────────────────


def test_parse_push_branch_push_returns_data():
    payload = _push_payload(ref="refs/heads/main", before="a" * 40, after="b" * 40)
    result = _parse_push(payload)
    assert result is not None
    assert result["target_branch"] == "main"
    assert result["target_sha"] == "b" * 40
    assert result["baseline_sha"] == "a" * 40
    assert result["repository_full_name"] == "org/repo"
    assert result["clone_url"] == "https://github.com/org/repo.git"


def test_parse_push_tag_push_returns_none():
    payload = _push_payload(ref="refs/tags/v1.0.0")
    assert _parse_push(payload) is None


def test_parse_push_branch_deletion_returns_none():
    payload = _push_payload(after="0" * 40)
    assert _parse_push(payload) is None


def test_parse_push_missing_ref_returns_none():
    payload = _push_payload()
    payload.pop("ref")
    assert _parse_push(payload) is None


# ── _parse_pull_request unit tests ───────────────────────────────────────────


def test_parse_pull_request_opened_returns_data():
    payload = _pr_payload(action="opened", head_sha="c" * 40, base_sha="d" * 40)
    result = _parse_pull_request(payload)
    assert result is not None
    assert result["target_sha"] == "c" * 40
    assert result["baseline_sha"] == "d" * 40
    assert result["target_branch"] == "feature/x"
    assert result["repository_full_name"] == "org/repo"


def test_parse_pull_request_synchronize_returns_data():
    assert _parse_pull_request(_pr_payload(action="synchronize")) is not None


def test_parse_pull_request_reopened_returns_data():
    assert _parse_pull_request(_pr_payload(action="reopened")) is not None


def test_parse_pull_request_closed_returns_none():
    assert _parse_pull_request(_pr_payload(action="closed")) is None


def test_parse_pull_request_edited_returns_none():
    assert _parse_pull_request(_pr_payload(action="edited")) is None


# ── Integration tests via AsyncClient ────────────────────────────────────────


def _make_app_with_mocks(mock_db: AsyncMock, mock_pool):
    """Build a FastAPI test app with overridden get_db and get_arq_pool."""
    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool
    return app


def _mock_db_with_run(run_id: uuid.UUID) -> AsyncMock:
    """Return an AsyncSession mock whose DAOs create a run with *run_id*."""
    mock_repo = MagicMock()
    mock_repo.repository_id = uuid.uuid4()
    mock_repo.clone_url = "https://github.com/org/repo.git"

    mock_run = MagicMock()
    mock_run.run_id = run_id

    mock_db = AsyncMock()

    # Patch RepositoryDAO and AnalysisRunDAO at the router level
    return mock_db, mock_repo, mock_run


@pytest.mark.asyncio
async def test_ping_event_returns_pong(monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    mock_db = AsyncMock()
    mock_pool = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/webhooks/github",
                content=b"{}",
                headers={"X-GitHub-Event": "ping"},
            )
        assert resp.status_code == 202
        assert resp.json()["message"] == "pong"
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_unknown_event_type_is_ignored(monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    mock_db = AsyncMock()
    mock_pool = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/webhooks/github",
                content=b'{"action":"created"}',
                headers={"X-GitHub-Event": "issue_comment"},
            )
        assert resp.status_code == 202
        assert "not handled" in resp.json()["message"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_invalid_signature_returns_403(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "real-secret")

    mock_db = AsyncMock()
    mock_pool = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    body = json.dumps(_push_payload()).encode()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": "sha256=badhash",
                },
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_valid_push_creates_run_and_returns_202(monkeypatch):
    """A valid signed push event creates a run and enqueues the pipeline."""
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    run_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.repository_id = uuid.uuid4()
    mock_repo.clone_url = "https://github.com/org/repo.git"

    mock_run = MagicMock()
    mock_run.run_id = run_id

    mock_db = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    body = json.dumps(_push_payload()).encode()

    try:
        with (
            patch("api_gateway.routers.webhook.RepositoryDAO") as MockRepoDAO,
            patch("api_gateway.routers.webhook.AnalysisRunDAO") as MockRunDAO,
        ):
            MockRepoDAO.return_value.get_by_full_name = AsyncMock(return_value=mock_repo)
            MockRunDAO.return_value.create = AsyncMock(return_value=mock_run)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/webhooks/github",
                    content=body,
                    headers={"X-GitHub-Event": "push"},
                )

        assert resp.status_code == 202
        data = resp.json()
        assert data["run_id"] == str(run_id)
        assert data["status"] == "queued"

        # ARQ job must be enqueued
        mock_pool.enqueue_job.assert_called_once_with("full_pipeline", str(run_id))

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_valid_pr_opened_creates_run_and_returns_202(monkeypatch):
    """A valid pull_request:opened event creates a run and enqueues the pipeline."""
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    run_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.repository_id = uuid.uuid4()
    mock_repo.clone_url = "https://github.com/org/repo.git"

    mock_run = MagicMock()
    mock_run.run_id = run_id

    mock_db = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    body = json.dumps(_pr_payload(action="opened")).encode()

    try:
        with (
            patch("api_gateway.routers.webhook.RepositoryDAO") as MockRepoDAO,
            patch("api_gateway.routers.webhook.AnalysisRunDAO") as MockRunDAO,
        ):
            MockRepoDAO.return_value.get_by_full_name = AsyncMock(return_value=mock_repo)
            MockRunDAO.return_value.create = AsyncMock(return_value=mock_run)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/webhooks/github",
                    content=body,
                    headers={"X-GitHub-Event": "pull_request"},
                )

        assert resp.status_code == 202
        data = resp.json()
        assert data["run_id"] == str(run_id)
        assert data["status"] == "queued"
        mock_pool.enqueue_job.assert_called_once_with("full_pipeline", str(run_id))

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_push_to_tag_is_ignored(monkeypatch):
    """A push to a tag ref returns ignored message without creating a run."""
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    mock_db = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    body = json.dumps(_push_payload(ref="refs/tags/v1.0.0")).encode()

    try:
        with (
            patch("api_gateway.routers.webhook.RepositoryDAO"),
            patch("api_gateway.routers.webhook.AnalysisRunDAO") as MockRunDAO,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/webhooks/github",
                    content=body,
                    headers={"X-GitHub-Event": "push"},
                )

        assert resp.status_code == 202
        assert "ignored" in resp.json()["message"]
        MockRunDAO.return_value.create.assert_not_called()
        mock_pool.enqueue_job.assert_not_called()

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_pool_none_does_not_crash(monkeypatch):
    """When no ARQ pool is configured the run is still created; just no enqueueing."""
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    run_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.repository_id = uuid.uuid4()
    mock_repo.clone_url = "https://github.com/org/repo.git"

    mock_run = MagicMock()
    mock_run.run_id = run_id

    mock_db = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: None  # pool unavailable

    body = json.dumps(_push_payload()).encode()

    try:
        with (
            patch("api_gateway.routers.webhook.RepositoryDAO") as MockRepoDAO,
            patch("api_gateway.routers.webhook.AnalysisRunDAO") as MockRunDAO,
        ):
            MockRepoDAO.return_value.get_by_full_name = AsyncMock(return_value=mock_repo)
            MockRunDAO.return_value.create = AsyncMock(return_value=mock_run)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/webhooks/github",
                    content=body,
                    headers={"X-GitHub-Event": "push"},
                )

        assert resp.status_code == 202
        assert resp.json()["run_id"] == str(run_id)

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_pr_closed_action_is_ignored(monkeypatch):
    """pull_request:closed event is not actionable — should be ignored."""
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)

    mock_db = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    body = json.dumps(_pr_payload(action="closed")).encode()

    try:
        with patch("api_gateway.routers.webhook.AnalysisRunDAO") as MockRunDAO:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/webhooks/github",
                    content=body,
                    headers={"X-GitHub-Event": "pull_request"},
                )

        assert resp.status_code == 202
        assert "ignored" in resp.json()["message"]
        MockRunDAO.return_value.create.assert_not_called()
        mock_pool.enqueue_job.assert_not_called()

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_valid_signature_accepted(monkeypatch):
    """A correctly-signed push event passes signature verification."""
    secret = "correct-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)

    run_id = uuid.uuid4()
    mock_repo = MagicMock()
    mock_repo.repository_id = uuid.uuid4()
    mock_repo.clone_url = "https://github.com/org/repo.git"

    mock_run = MagicMock()
    mock_run.run_id = run_id

    mock_db = AsyncMock()
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock()

    from api_gateway.dependencies import get_db
    from api_gateway.main import app
    from api_gateway.queue import get_arq_pool

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_arq_pool] = lambda: mock_pool

    body = json.dumps(_push_payload()).encode()
    sig = _sign(secret, body)

    try:
        with (
            patch("api_gateway.routers.webhook.RepositoryDAO") as MockRepoDAO,
            patch("api_gateway.routers.webhook.AnalysisRunDAO") as MockRunDAO,
        ):
            MockRepoDAO.return_value.get_by_full_name = AsyncMock(return_value=mock_repo)
            MockRunDAO.return_value.create = AsyncMock(return_value=mock_run)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/webhooks/github",
                    content=body,
                    headers={
                        "X-GitHub-Event": "push",
                        "X-Hub-Signature-256": sig,
                    },
                )

        assert resp.status_code == 202
        assert resp.json()["run_id"] == str(run_id)

    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_arq_pool, None)
