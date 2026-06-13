from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from devmanager_reporting.service import AlreadyReportedError, ReportError, generate_report


def _make_run(run_id: uuid.UUID) -> MagicMock:
    m = MagicMock()
    m.run_id = run_id
    m.repository_id = uuid.uuid4()
    m.status = "scored"
    m.target_branch = "main"
    m.target_sha = "abc1234"
    m.baseline_sha = "def5678"
    m.started_at = None
    m.completed_at = None
    return m


def _make_repo(full_name: str = "org/repo") -> MagicMock:
    m = MagicMock()
    m.full_name = full_name
    return m


def _make_score() -> MagicMock:
    m = MagicMock()
    m.score_id = uuid.uuid4()
    m.final_score = 85.0
    m.grade = "B"
    m.confidence = 0.85
    m.scoring_version = "v1"
    m.deductions = []
    m.caps = []
    m.limitations = []
    return m


def _make_report(run_id: uuid.UUID) -> MagicMock:
    m = MagicMock()
    m.report_id = uuid.uuid4()
    m.run_id = run_id
    m.content_reference = f"file:///tmp/devmanager/reports/{run_id}.md"
    m.generated_at = MagicMock()
    m.generated_at.isoformat.return_value = "2026-06-07T10:00:00+00:00"
    return m


@pytest.mark.asyncio
async def test_generate_report_raises_when_run_not_found():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    with patch("devmanager_reporting.service.AnalysisRunDAO") as MockRunDAO:
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(ReportError, match=str(run_id)):
            await generate_report(run_id, mock_db)


@pytest.mark.asyncio
async def test_generate_report_raises_when_already_exists():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    with (
        patch("devmanager_reporting.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_reporting.service.ReportDAO") as MockReportDAO,
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockReportDAO.return_value.get_by_run = AsyncMock(return_value=_make_report(run_id))

        with pytest.raises(AlreadyReportedError):
            await generate_report(run_id, mock_db)


@pytest.mark.asyncio
async def test_generate_report_creates_file_and_db_record(tmp_path, monkeypatch):
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_report = _make_report(run_id)

    monkeypatch.setenv("REPORTS_DIR", str(tmp_path))

    # Re-import to pick up the env var — patch the module-level path
    import devmanager_reporting.service as svc_module

    monkeypatch.setattr(svc_module, "_REPORTS_ROOT", tmp_path)

    with (
        patch("devmanager_reporting.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_reporting.service.RepositoryDAO") as MockRepoDAO,
        patch("devmanager_reporting.service.ScoreDAO") as MockScoreDAO,
        patch("devmanager_reporting.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_reporting.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_reporting.service.ReportDAO") as MockReportDAO,
        patch("devmanager_reporting.service.AuditEventDAO") as MockAuditDAO,
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockRepoDAO.return_value.get_by_id = AsyncMock(return_value=_make_repo("org/repo"))
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=_make_score())
        MockFindingDAO.return_value.list_by_run = AsyncMock(return_value=[])
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[])
        MockReportDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockReportDAO.return_value.create = AsyncMock(return_value=mock_report)
        MockAuditDAO.return_value.append = AsyncMock()

        report = await generate_report(run_id, mock_db)

    assert report is mock_report
    MockReportDAO.return_value.create.assert_called_once()
    call_kwargs = MockReportDAO.return_value.create.call_args.kwargs
    assert call_kwargs["run_id"] == run_id
    assert call_kwargs["status"] == "generated"
    assert "file://" in call_kwargs["content_reference"]


@pytest.mark.asyncio
async def test_generate_report_commits_db(tmp_path, monkeypatch):
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    import devmanager_reporting.service as svc_module

    monkeypatch.setattr(svc_module, "_REPORTS_ROOT", tmp_path)

    with (
        patch("devmanager_reporting.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_reporting.service.RepositoryDAO") as MockRepoDAO,
        patch("devmanager_reporting.service.ScoreDAO") as MockScoreDAO,
        patch("devmanager_reporting.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_reporting.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_reporting.service.ReportDAO") as MockReportDAO,
        patch("devmanager_reporting.service.AuditEventDAO") as MockAuditDAO,
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockRepoDAO.return_value.get_by_id = AsyncMock(return_value=_make_repo())
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockFindingDAO.return_value.list_by_run = AsyncMock(return_value=[])
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[])
        MockReportDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockReportDAO.return_value.create = AsyncMock(return_value=_make_report(run_id))
        MockAuditDAO.return_value.append = AsyncMock()

        await generate_report(run_id, mock_db)

    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_generate_report_emits_audit_event(tmp_path, monkeypatch):
    run_id = uuid.uuid4()
    mock_db = AsyncMock()

    import devmanager_reporting.service as svc_module

    monkeypatch.setattr(svc_module, "_REPORTS_ROOT", tmp_path)

    with (
        patch("devmanager_reporting.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_reporting.service.RepositoryDAO") as MockRepoDAO,
        patch("devmanager_reporting.service.ScoreDAO") as MockScoreDAO,
        patch("devmanager_reporting.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_reporting.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_reporting.service.ReportDAO") as MockReportDAO,
        patch("devmanager_reporting.service.AuditEventDAO") as MockAuditDAO,
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_make_run(run_id))
        MockRepoDAO.return_value.get_by_id = AsyncMock(return_value=_make_repo())
        MockScoreDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockFindingDAO.return_value.list_by_run = AsyncMock(return_value=[])
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[])
        MockReportDAO.return_value.get_by_run = AsyncMock(return_value=None)
        MockReportDAO.return_value.create = AsyncMock(return_value=_make_report(run_id))
        MockAuditDAO.return_value.append = AsyncMock()

        await generate_report(run_id, mock_db)

    MockAuditDAO.return_value.append.assert_called_once()
    call_kwargs = MockAuditDAO.return_value.append.call_args.kwargs
    assert call_kwargs["event_type"] == "run.report_generated"
    assert call_kwargs["actor"] == "system"
    assert call_kwargs["workflow_id"] == run_id
