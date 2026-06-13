from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from devmanager_scoring.service import AlreadyScoredError, ScoreError, score_run


def _make_run(run_id: uuid.UUID) -> MagicMock:
    m = MagicMock()
    m.run_id = run_id
    m.status = "agent_review_completed"
    return m


def _make_score(run_id: uuid.UUID) -> MagicMock:
    m = MagicMock()
    m.score_id = uuid.uuid4()
    m.run_id = run_id
    m.final_score = 85.0
    m.grade = "B"
    return m


def _make_finding(finding_id: str, severity: str = "medium", confidence: float = 1.0) -> MagicMock:
    m = MagicMock()
    m.finding_id = finding_id
    m.category = "correctness"
    m.severity = severity
    m.confidence = confidence
    m.dedupe_key = finding_id
    return m


@pytest.mark.asyncio
async def test_score_run_raises_when_run_not_found():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    with patch("devmanager_scoring.service.AnalysisRunDAO") as MockRunDAO:
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ScoreError, match=str(run_id)):
            await score_run(run_id, mock_db)


@pytest.mark.asyncio
async def test_score_run_raises_when_already_scored():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    with (
        patch("devmanager_scoring.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_scoring.service.ScoreDAO") as MockScoreDAO,
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=_make_score(run_id))

        with pytest.raises(AlreadyScoredError):
            await score_run(run_id, mock_db)


@pytest.mark.asyncio
async def test_score_run_no_findings_perfect_score():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_score = _make_score(run_id)

    with (
        patch("devmanager_scoring.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_scoring.service.ScoreDAO") as MockScoreDAO,
        patch("devmanager_scoring.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_scoring.service.AuditEventDAO"),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockScoreDAO.return_value.create = AsyncMock(return_value=mock_score)
        MockFindingDAO.return_value.list_by_run = AsyncMock(return_value=[])

        score = await score_run(run_id, mock_db)

    assert score is mock_score
    call_kwargs = MockScoreDAO.return_value.create.call_args.kwargs
    assert call_kwargs["final_score"] == 100.0
    assert call_kwargs["grade"] == "A"
    assert call_kwargs["status"] == "complete"


@pytest.mark.asyncio
async def test_score_run_with_findings_deducts():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_score = _make_score(run_id)

    findings = [
        _make_finding("F-001", "high", 1.0),  # −10
        _make_finding("F-002", "medium", 1.0),  # −5
    ]

    with (
        patch("devmanager_scoring.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_scoring.service.ScoreDAO") as MockScoreDAO,
        patch("devmanager_scoring.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_scoring.service.AuditEventDAO"),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockScoreDAO.return_value.create = AsyncMock(return_value=mock_score)
        MockFindingDAO.return_value.list_by_run = AsyncMock(return_value=findings)

        await score_run(run_id, mock_db)

    kwargs = MockScoreDAO.return_value.create.call_args.kwargs
    assert kwargs["final_score"] == 85.0
    assert kwargs["grade"] == "B"
    assert len(kwargs["deductions"]) == 2


@pytest.mark.asyncio
async def test_score_run_updates_run_status():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    with (
        patch("devmanager_scoring.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_scoring.service.ScoreDAO") as MockScoreDAO,
        patch("devmanager_scoring.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_scoring.service.AuditEventDAO"),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockScoreDAO.return_value.create = AsyncMock(return_value=_make_score(run_id))
        MockFindingDAO.return_value.list_by_run = AsyncMock(return_value=[])

        await score_run(run_id, mock_db)

    MockRunDAO.return_value.update_status.assert_called_once_with(run_id, "scored")


@pytest.mark.asyncio
async def test_score_run_commits_db():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    with (
        patch("devmanager_scoring.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_scoring.service.ScoreDAO") as MockScoreDAO,
        patch("devmanager_scoring.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_scoring.service.AuditEventDAO"),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockScoreDAO.return_value.create = AsyncMock(return_value=_make_score(run_id))
        MockFindingDAO.return_value.list_by_run = AsyncMock(return_value=[])

        await score_run(run_id, mock_db)

    mock_db.commit.assert_called_once()
