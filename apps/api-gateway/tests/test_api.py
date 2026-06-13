from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api_gateway.main import app
from httpx import ASGITransport, AsyncClient

BASE = "http://test"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_repo(full_name: str = "test-org/test-repo"):
    m = MagicMock()
    m.repository_id = uuid.uuid4()
    m.full_name = full_name
    m.status = "active"
    return m


def _mock_run(
    repo_id: uuid.UUID | None = None,
    status: str = "trigger_received",
    full_name: str = "test-org/test-repo",
):
    m = MagicMock()
    m.run_id = uuid.uuid4()
    m.repository_id = repo_id or uuid.uuid4()
    m.repository_full_name = full_name
    m.trigger_id = None
    m.trigger_type = "manual"
    m.target_branch = "main"
    m.baseline_sha = "0" * 40
    m.target_sha = "0" * 40
    m.merge_base_sha = None
    m.history_rewrite_detected = False
    m.status = status
    m.policy_version = "v1"
    m.scoring_version = "v1"
    m.agent_versions = {}
    m.failure_reason = None
    m.started_at = datetime.now(UTC)
    m.completed_at = None
    return m


# ── Health ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── POST /v1/analysis-runs ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_analysis_run_returns_202():
    mock_repo = _mock_repo()
    mock_run = _mock_run(mock_repo.repository_id)

    with (
        patch("api_gateway.routers.analysis_runs.RepositoryDAO") as MockRepoDAO,
        patch("api_gateway.routers.analysis_runs.BaselineDAO") as MockBaselineDAO,
        patch("api_gateway.routers.analysis_runs.AnalysisRunDAO") as MockRunDAO,
    ):
        MockRepoDAO.return_value.get_by_full_name = AsyncMock(return_value=mock_repo)
        MockBaselineDAO.return_value.get = AsyncMock(return_value=None)
        MockRunDAO.return_value.create = AsyncMock(return_value=mock_run)

        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            with (
                patch("api_gateway.routers.analysis_runs.select"),
                patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock),
                patch("sqlalchemy.ext.asyncio.AsyncSession.execute", new_callable=AsyncMock),
            ):
                resp = await client.post(
                    "/v1/analysis-runs",
                    json={"repository": "test-org/test-repo", "target_branch": "main"},
                )

    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "trigger_received"


@pytest.mark.asyncio
async def test_create_analysis_run_bad_repository_format():
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            "/v1/analysis-runs",
            json={"repository": "invalid-no-slash", "target_branch": "main"},
        )
    assert resp.status_code == 422


# ── GET /v1/analysis-runs/{run_id} ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_analysis_run_not_found():
    with patch("api_gateway.routers.analysis_runs.AnalysisRunDAO") as MockRunDAO:
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", new_callable=AsyncMock):
                resp = await client.get(f"/v1/analysis-runs/{uuid.uuid4()}")

    assert resp.status_code == 404
    data = resp.json()
    assert "error_code" in data
    assert "message" in data


# ── GET .../score not found ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_score_not_found():
    with patch("api_gateway.routers.analysis_runs.ScoreDAO") as MockScoreDAO:
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", new_callable=AsyncMock):
                resp = await client.get(f"/v1/analysis-runs/{uuid.uuid4()}/score")

    assert resp.status_code == 404


# ── POST /v1/publication-requests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_publication_request_external_channel_denied():
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            "/v1/publication-requests",
            json={
                "report_id": str(uuid.uuid4()),
                "channel": "slack",
                "destination": "#alerts",
                "content_reference": "file:///tmp/report.md",
            },
        )
    assert resp.status_code == 202
    assert resp.json()["policy_decision"] == "denied"


@pytest.mark.asyncio
async def test_publication_request_internal_markdown_allowed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            "/v1/publication-requests",
            json={
                "report_id": str(uuid.uuid4()),
                "channel": "internal_markdown",
                "destination": "file:///tmp/report.md",
                "content_reference": "file:///tmp/report.md",
            },
        )
    assert resp.status_code == 202
    assert resp.json()["policy_decision"] == "allowed"


# ── GET /v1/audit-events ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_audit_events_returns_items_key():
    with patch("api_gateway.routers.audit_events.select"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            with patch(
                "sqlalchemy.ext.asyncio.AsyncSession.execute", new_callable=AsyncMock
            ) as mock_exec:
                mock_result = MagicMock()
                mock_result.scalars.return_value.all.return_value = []
                mock_exec.return_value = mock_result
                resp = await client.get("/v1/audit-events")

    assert resp.status_code == 200
    assert "items" in resp.json()


# ── POST /v1/analysis-runs/{run_id}/retry ─────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_run_creates_new_run_with_trigger_id_lineage():
    """A retry on a failed run creates a NEW run_id, a new TriggerEvent
    of event_type='retry' (since analysis_runs.trigger_id is FK-bound to
    trigger_events.event_id, NOT to runs.run_id), and copies the original's
    target_branch / baseline_sha / target_sha. The original run_id is
    stashed in the trigger event's raw_payload for lineage."""
    original = _mock_run(status="failed")
    new_run = _mock_run(repo_id=original.repository_id, status="trigger_received")
    fake_event = MagicMock()
    fake_event.event_id = uuid.uuid4()

    run_create_kwargs: dict = {}
    event_create_kwargs: dict = {}

    async def _capture_run_create(**kwargs):
        run_create_kwargs.update(kwargs)
        return new_run

    async def _capture_event_create(**kwargs):
        event_create_kwargs.update(kwargs)
        return fake_event

    mock_arq = MagicMock()
    mock_arq.enqueue_job = AsyncMock()

    with (
        patch("api_gateway.routers.analysis_runs.AnalysisRunDAO") as MockRunDAO,
        patch("api_gateway.routers.analysis_runs.TriggerEventDAO") as MockEventDAO,
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=original)
        MockRunDAO.return_value.create = AsyncMock(side_effect=_capture_run_create)
        MockEventDAO.return_value.create = AsyncMock(side_effect=_capture_event_create)
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock):
                app.state.arq_pool = mock_arq
                try:
                    resp = await client.post(
                        f"/v1/analysis-runs/{original.run_id}/retry",
                    )
                finally:
                    del app.state.arq_pool

    assert resp.status_code == 202
    data = resp.json()
    assert data["run_id"] == str(new_run.run_id)
    assert data["status"] == "trigger_received"
    # The new run's trigger_id points to the freshly-created TriggerEvent,
    # NOT to the original run_id (which would violate the FK).
    assert run_create_kwargs["trigger_id"] == fake_event.event_id
    assert run_create_kwargs["repository_id"] == original.repository_id
    assert run_create_kwargs["target_branch"] == original.target_branch
    assert run_create_kwargs["baseline_sha"] == original.baseline_sha
    assert run_create_kwargs["target_sha"] == original.target_sha
    # The trigger event carries the lineage to the original run.
    assert event_create_kwargs["event_type"] == "retry"
    assert event_create_kwargs["source"] == "manual"
    assert event_create_kwargs["raw_payload"]["retry_of_run_id"] == str(original.run_id)
    # Pipeline job should be enqueued for the new run.
    mock_arq.enqueue_job.assert_awaited_once_with("full_pipeline", str(new_run.run_id))


@pytest.mark.asyncio
async def test_retry_run_returns_404_when_not_found():
    with patch("api_gateway.routers.analysis_runs.AnalysisRunDAO") as MockRunDAO:
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            resp = await client.post(f"/v1/analysis-runs/{uuid.uuid4()}/retry")

    assert resp.status_code == 404
    assert "not found" in resp.json()["message"].lower()


@pytest.mark.parametrize(
    "non_retryable_status",
    [
        "trigger_received",
        "ingestion_started",
        "completed",
        "scoring_completed",
    ],
)
@pytest.mark.asyncio
async def test_retry_run_returns_409_for_non_retryable_status(non_retryable_status):
    """Only failed / partial_analysis / rejected runs can be retried; an
    in-progress or completed run returns 409."""
    run = _mock_run(status=non_retryable_status)
    with patch("api_gateway.routers.analysis_runs.AnalysisRunDAO") as MockRunDAO:
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=run)
        MockRunDAO.return_value.create = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
            resp = await client.post(f"/v1/analysis-runs/{run.run_id}/retry")

    assert resp.status_code == 409
    assert non_retryable_status in resp.json()["message"]
    # `create` must NOT be called when the status is non-retryable.
    MockRunDAO.return_value.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_run_works_for_all_retryable_statuses():
    """A retry should be allowed for failed, partial_analysis, and rejected."""
    for status in ("failed", "partial_analysis", "rejected"):
        original = _mock_run(status=status)
        new_run = _mock_run(repo_id=original.repository_id, status="trigger_received")
        fake_event = MagicMock()
        fake_event.event_id = uuid.uuid4()
        mock_arq = MagicMock()
        mock_arq.enqueue_job = AsyncMock()

        with (
            patch("api_gateway.routers.analysis_runs.AnalysisRunDAO") as MockRunDAO,
            patch("api_gateway.routers.analysis_runs.TriggerEventDAO") as MockEventDAO,
        ):
            MockRunDAO.return_value.get_by_id = AsyncMock(return_value=original)
            MockRunDAO.return_value.create = AsyncMock(return_value=new_run)
            MockEventDAO.return_value.create = AsyncMock(return_value=fake_event)
            async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
                with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", new_callable=AsyncMock):
                    app.state.arq_pool = mock_arq
                    try:
                        resp = await client.post(
                            f"/v1/analysis-runs/{original.run_id}/retry",
                        )
                    finally:
                        del app.state.arq_pool

        assert resp.status_code == 202, f"status={status} got {resp.status_code}"
