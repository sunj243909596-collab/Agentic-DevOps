"""
Tests for worker/tasks.py — full_pipeline ARQ task.

All DB, service, and Anthropic calls are mocked; no real Redis or Postgres needed.

Import-mode note: we use --import-mode=importlib (set in root pyproject.toml),
so patching must use the fully-qualified import path that *tasks.py* actually uses.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_session_factory(session: AsyncMock | None = None):
    """Return an async context-manager factory that yields *session*."""
    if session is None:
        session = AsyncMock()

    @asynccontextmanager
    async def _factory():
        yield session

    return _factory


def _make_ctx(session: AsyncMock | None = None) -> dict:
    """Build a minimal ARQ ctx dict."""
    return {"make_session": _make_session_factory(session)}


def _run_id() -> str:
    return str(uuid.uuid4())


def _mock_run_for_pipeline(run_id: str, repository_id: uuid.UUID | None = None) -> MagicMock:
    run = MagicMock()
    run.run_id = uuid.UUID(run_id)
    run.repository_id = repository_id or uuid.uuid4()
    run.status = "git_ingested"
    return run


def _setup_repo(tmp_path: Path, run_id: str):
    """Prepare repo dir + mock run for review phase tests."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "HEAD").touch()
    return repo_dir, _mock_run_for_pipeline(run_id)


# ── full_pipeline ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_pipeline_calls_all_phases_in_order(monkeypatch, tmp_path):
    """When an API key is present, all 4 service calls happen in sequence."""
    run_id = _run_id()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    call_order: list[str] = []

    async def fake_ingest(rid, db):
        call_order.append("ingest")

    async def fake_review(rid, db, provider, **kw):
        call_order.append("review")
        return []

    async def fake_score(rid, db):
        call_order.append("score")
        return MagicMock()

    async def fake_report(rid, db):
        call_order.append("report")
        return MagicMock()

    ctx = _make_ctx()
    repo_dir, mock_run = _setup_repo(tmp_path, run_id)

    with (
        patch("worker.tasks.ingest", fake_ingest),
        patch("worker.tasks.score_run", fake_score),
        patch("worker.tasks.generate_report", fake_report),
        patch(
            "worker.tasks._load_llm_provider", new=AsyncMock(return_value=MagicMock(name="mock"))
        ),
        patch("worker.tasks._resolve_repo_dir", return_value=repo_dir),
        patch("worker.tasks.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.review_run", fake_review),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=mock_run)
        MockRunDAO.return_value.update_status = AsyncMock()

        from worker.tasks import full_pipeline

        result = await full_pipeline(ctx, run_id)

    assert call_order == ["ingest", "review", "score", "report"]
    assert result["status"] == "completed"
    assert result["run_id"] == run_id
    completed_calls = [
        c for c in MockRunDAO.return_value.update_status.await_args_list if c.args[1] == "completed"
    ]
    assert completed_calls, "full_pipeline must mark run completed after report"


@pytest.mark.asyncio
async def test_full_pipeline_skips_review_without_api_key(monkeypatch):
    """Without an API key, review is skipped and status is advanced manually."""
    run_id = _run_id()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    phases: list[str] = []

    async def fake_ingest(rid, db):
        phases.append("ingest")

    async def fake_score(rid, db):
        phases.append("score")
        return MagicMock()

    async def fake_report(rid, db):
        phases.append("report")
        return MagicMock()

    mock_session = AsyncMock()
    mock_run_dao = MagicMock()
    mock_run_dao.update_status = AsyncMock()

    ctx = _make_ctx(mock_session)

    with (
        patch("worker.tasks.ingest", fake_ingest),
        patch("worker.tasks.score_run", fake_score),
        patch("worker.tasks.generate_report", fake_report),
        patch("worker.tasks._load_llm_provider", new=AsyncMock(return_value=None)),
        patch("worker.tasks.AnalysisRunDAO", return_value=mock_run_dao),
    ):
        from worker.tasks import full_pipeline

        result = await full_pipeline(ctx, run_id)

    assert "review" not in phases
    assert phases == ["ingest", "score", "report"]
    # full_pipeline marks BOTH 'agent_review_completed' (skip-review path,
    # tasks.py:130) AND 'completed' (final wrap-up, tasks.py:143). Asserting
    # the former as a substring of the call args keeps the test honest about
    # the pipeline's two-phase status progression.
    agent_review_calls = [
        c
        for c in mock_run_dao.update_status.call_args_list
        if c.args[1] == "agent_review_completed"
    ]
    assert agent_review_calls, "full_pipeline must mark agent_review_completed when no API key"
    assert any(c.args[1] == "completed" for c in mock_run_dao.update_status.call_args_list), (
        "full_pipeline must mark run completed at end of pipeline"
    )
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_full_pipeline_marks_run_failed_on_ingest_error(monkeypatch):
    """When ingest raises, the run is marked failed and the exception propagates."""
    run_id = _run_id()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    async def bad_ingest(rid, db):
        raise RuntimeError("network error")

    mock_session = AsyncMock()
    mock_run_dao = MagicMock()
    mock_run_dao.update_status = AsyncMock()

    ctx = _make_ctx(mock_session)

    with (
        patch("worker.tasks.ingest", bad_ingest),
        patch("worker.tasks.AnalysisRunDAO", return_value=mock_run_dao),
    ):
        from worker.tasks import full_pipeline

        with pytest.raises(RuntimeError, match="network error"):
            await full_pipeline(ctx, run_id)

    mock_run_dao.update_status.assert_called_with(
        uuid.UUID(run_id), "failed", failure_reason="network error"
    )


@pytest.mark.asyncio
async def test_full_pipeline_marks_run_failed_on_score_error(monkeypatch, tmp_path):
    """When scoring raises, the run is marked failed and the exception propagates."""
    run_id = _run_id()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    phases: list[str] = []

    async def fake_ingest(rid, db):
        phases.append("ingest")

    async def bad_score(rid, db):
        raise ValueError("score error")

    mock_session = AsyncMock()
    mock_run_dao = MagicMock()
    mock_run_dao.update_status = AsyncMock()

    ctx = _make_ctx(mock_session)
    repo_dir, mock_run = _setup_repo(tmp_path, run_id)

    with (
        patch("worker.tasks.ingest", fake_ingest),
        patch("worker.tasks.score_run", bad_score),
        patch(
            "worker.tasks._load_llm_provider", new=AsyncMock(return_value=MagicMock(name="mock"))
        ),
        patch("worker.tasks._resolve_repo_dir", return_value=repo_dir),
        patch("worker.tasks.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.review_run", new=AsyncMock(return_value=[])),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=mock_run)
        MockRunDAO.return_value.update_status = AsyncMock(side_effect=mock_run_dao.update_status)

        from worker.tasks import full_pipeline

        with pytest.raises(ValueError, match="score error"):
            await full_pipeline(ctx, run_id)

    call_statuses = [c.args[1] for c in mock_run_dao.update_status.call_args_list]
    assert "failed" in call_statuses


@pytest.mark.asyncio
async def test_full_pipeline_result_contains_run_id(monkeypatch, tmp_path):
    """Successful pipeline result includes the run_id string."""
    run_id = _run_id()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    async def noop(*a, **kw):
        return MagicMock()

    mock_session = AsyncMock()
    mock_run_dao = MagicMock()
    mock_run_dao.update_status = AsyncMock()

    ctx = _make_ctx(mock_session)
    repo_dir, mock_run = _setup_repo(tmp_path, run_id)

    with (
        patch("worker.tasks.ingest", noop),
        patch("worker.tasks.score_run", noop),
        patch("worker.tasks.generate_report", noop),
        patch(
            "worker.tasks._load_llm_provider", new=AsyncMock(return_value=MagicMock(name="mock"))
        ),
        patch("worker.tasks._resolve_repo_dir", return_value=repo_dir),
        patch("worker.tasks.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.review_run", new=AsyncMock(return_value=[])),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=mock_run)
        MockRunDAO.return_value.update_status = AsyncMock(side_effect=mock_run_dao.update_status)

        from worker.tasks import full_pipeline

        result = await full_pipeline(ctx, run_id)

    assert result["run_id"] == run_id


@pytest.mark.asyncio
async def test_full_pipeline_aborts_on_review_timeout(tmp_path):
    """If review_run hangs longer than the timeout, the run is marked failed."""
    from worker.tasks import full_pipeline

    run_id_str = str(uuid.uuid4())
    ctx = {"make_session": _make_session_factory(AsyncMock())}

    async def hanging_review(*a, **kw):
        await asyncio.sleep(60)
        return []

    mock_run = _mock_run_for_pipeline(run_id_str)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "HEAD").touch()

    with (
        patch("worker.tasks.ingest", new=AsyncMock()),
        patch("worker.tasks._load_llm_provider", new=AsyncMock(return_value=MagicMock())),
        patch("worker.tasks._resolve_repo_dir", return_value=repo_dir),
        patch("worker.tasks.score_run", new=AsyncMock()),
        patch("worker.tasks.generate_report", new=AsyncMock()),
        patch("worker.tasks.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.review_run", hanging_review),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=mock_run)
        MockRunDAO.return_value.update_status = AsyncMock()

        with pytest.raises(asyncio.TimeoutError):
            await full_pipeline(ctx, run_id_str, review_timeout_sec=0.5)

        update_calls = MockRunDAO.return_value.update_status.await_args_list
        assert any(c.args[1] == "failed" for c in update_calls), (
            f"expected update_status('failed'), got: {update_calls}"
        )


# ── startup / shutdown ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_startup_creates_engine_and_session_factory(monkeypatch):
    """startup() stores engine and make_session in ctx."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://test:test@localhost:5432/test",
    )

    ctx: dict = {}

    mock_engine = MagicMock()
    mock_factory = MagicMock()

    with (
        patch("worker.main.create_async_engine", return_value=mock_engine) as mock_cae,
        patch("worker.main.async_sessionmaker", return_value=mock_factory) as mock_sm,
    ):
        from worker.main import startup

        await startup(ctx)

    assert ctx["engine"] is mock_engine
    assert ctx["make_session"] is mock_factory
    mock_cae.assert_called_once()
    mock_sm.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_disposes_engine():
    """shutdown() calls engine.dispose() when engine is in ctx."""
    mock_engine = AsyncMock()
    ctx = {"engine": mock_engine}

    from worker.main import shutdown

    await shutdown(ctx)

    mock_engine.dispose.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_is_noop_without_engine():
    """shutdown() does nothing when ctx has no engine key."""
    ctx: dict = {}

    from worker.main import shutdown

    await shutdown(ctx)  # must not raise
