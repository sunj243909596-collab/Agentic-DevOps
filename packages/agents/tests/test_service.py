from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from devmanager_agents.service import ReviewError, _dedupe_key, review_run

# ── _dedupe_key ───────────────────────────────────────────────────────────────


def test_dedupe_key_is_deterministic():
    k1 = _dedupe_key("org/repo", "src/a.py", "security", 42, "SQL injection")
    k2 = _dedupe_key("org/repo", "src/a.py", "security", 42, "SQL injection")
    assert k1 == k2


def test_dedupe_key_differs_on_different_inputs():
    k1 = _dedupe_key("org/repo", "src/a.py", "security", 42, "SQL injection")
    k2 = _dedupe_key("org/repo", "src/a.py", "security", 43, "SQL injection")
    assert k1 != k2


def test_dedupe_key_length():
    k = _dedupe_key("org/repo", "f.py", "correctness", 1, "bug")
    assert len(k) == 16


# ── review_run (mocked AgentReviewer + DB) ─────────────────────────────────────


def _make_finding_response(category: str, file: str = "src/main.py") -> list[dict]:
    return [
        {
            "category": category,
            "severity": "medium",
            "confidence": 0.8,
            "file": file,
            "start_line": 10,
            "end_line": 15,
            "observation": "Potential issue in this code",
            "impact": "Could cause problems at runtime",
            "recommendation": "Refactor this section",
            "verification": "Add a unit test for this path",
            "evidence_refs": [f"diff:{file}:10-15"],
        }
    ]


def _mock_provider():
    provider = MagicMock()
    provider.name = "mock"
    provider.complete = AsyncMock()
    return provider


def _mock_run(run_id: uuid.UUID, target_sha: str = "abc1234") -> MagicMock:
    m = MagicMock()
    m.run_id = run_id
    m.target_sha = target_sha
    m.status = "git_ingested"
    return m


def _mock_unit(file_path: str = "src/main.py") -> MagicMock:
    m = MagicMock()
    m.change_unit_id = uuid.uuid4()
    m.file_path = file_path
    m.language = "python"
    m.change_type = "modified"
    m.risk_tags = []
    m.added_lines = 10
    m.deleted_lines = 5
    m.hunks_ref = None
    m.repository_full_name = "test-org/test-repo"
    m.is_binary = False
    m.is_generated = False
    m.is_vendor = False
    return m


@pytest.mark.asyncio
async def test_review_run_no_reviewable_units():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_provider = _mock_provider()

    with (
        patch("devmanager_agents.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_agents.service.FindingDAO"),
        patch("devmanager_agents.service.AuditEventDAO"),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_mock_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()

        binary_unit = _mock_unit()
        binary_unit.is_binary = True
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[binary_unit])

        findings = await review_run(run_id, mock_db, mock_provider)

    assert findings == []


@pytest.mark.asyncio
async def test_review_run_run_not_found_raises():
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_provider = _mock_provider()

    with patch("devmanager_agents.service.AnalysisRunDAO") as MockRunDAO:
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(ReviewError):
            await review_run(run_id, mock_db, mock_provider)


def _ensure_unit_on_disk(tmp_path, unit) -> None:
    p = tmp_path / unit.file_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("sample code\n" * max(unit.added_lines, 1))


@pytest.mark.asyncio
async def test_review_run_persists_valid_findings(tmp_path):
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_provider = _mock_provider()

    mock_finding = MagicMock()
    mock_finding.finding_id = "F-20260607-001"

    mock_reviewer = MagicMock()
    mock_reviewer.review_all = AsyncMock(return_value=_make_finding_response("correctness"))

    unit = _mock_unit()
    _ensure_unit_on_disk(tmp_path, unit)

    with (
        patch("devmanager_agents.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_agents.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_agents.service.AuditEventDAO"),
        patch("devmanager_agents.service.AgentReviewer", return_value=mock_reviewer),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_mock_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[unit])
        MockFindingDAO.return_value.create = AsyncMock(return_value=mock_finding)

        findings = await review_run(
            run_id,
            mock_db,
            mock_provider,
            concurrency=1,
            repo_dir=tmp_path,
        )

    assert MockFindingDAO.return_value.create.call_count == 1
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_review_run_skips_invalid_findings(tmp_path):
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_provider = _mock_provider()

    bad_finding = {
        "category": "correctness",
        "severity": "medium",
        "confidence": 0.8,
        "file": "src/main.py",
        "start_line": 10,
        "end_line": 15,
        "evidence_refs": ["diff:src/main.py:10-15"],
    }
    mock_reviewer = MagicMock()
    mock_reviewer.review_all = AsyncMock(return_value=[bad_finding])

    unit = _mock_unit()
    _ensure_unit_on_disk(tmp_path, unit)

    with (
        patch("devmanager_agents.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_agents.service.FindingDAO") as MockFindingDAO,
        patch("devmanager_agents.service.AuditEventDAO"),
        patch("devmanager_agents.service.AgentReviewer", return_value=mock_reviewer),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_mock_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[unit])
        MockFindingDAO.return_value.create = AsyncMock(return_value=MagicMock())

        await review_run(run_id, mock_db, mock_provider, concurrency=1, repo_dir=tmp_path)

    MockRunDAO.return_value.update_status.assert_called()


@pytest.mark.asyncio
async def test_review_run_status_updated_on_completion(tmp_path):
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_provider = _mock_provider()

    mock_reviewer = MagicMock()
    mock_reviewer.review_all = AsyncMock(return_value=[])

    unit = _mock_unit()
    _ensure_unit_on_disk(tmp_path, unit)

    with (
        patch("devmanager_agents.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_agents.service.FindingDAO"),
        patch("devmanager_agents.service.AuditEventDAO"),
        patch("devmanager_agents.service.AgentReviewer", return_value=mock_reviewer),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_mock_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[unit])

        await review_run(run_id, mock_db, mock_provider, concurrency=1, repo_dir=tmp_path)

    calls = [c.args[1] for c in MockRunDAO.return_value.update_status.call_args_list]
    assert "agent_review_started" in calls
    assert "agent_review_completed" in calls


@pytest.mark.asyncio
async def test_review_run_skips_oversized_or_trivial_units(tmp_path, monkeypatch):
    run_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_provider = _mock_provider()

    big_unit = _mock_unit("huge.json")
    big_unit.added_lines = 2000
    big_unit.hunks_ref = None

    tiny_unit = _mock_unit("a.py")
    tiny_unit.added_lines = 1
    tiny_unit.deleted_lines = 1

    (tmp_path / "huge.json").write_text("x" * 60_000)
    (tmp_path / "a.py").write_text("x = 1\n")

    mock_reviewer = MagicMock()
    mock_reviewer.review_all = AsyncMock(return_value=[])

    with (
        patch("devmanager_agents.service.AnalysisRunDAO") as MockRunDAO,
        patch("devmanager_agents.service.ChangeUnitDAO") as MockCUDAO,
        patch("devmanager_agents.service.FindingDAO"),
        patch("devmanager_agents.service.AuditEventDAO"),
        patch("devmanager_agents.service.AgentReviewer", return_value=mock_reviewer),
    ):
        MockRunDAO.return_value.get_by_id = AsyncMock(return_value=_mock_run(run_id))
        MockRunDAO.return_value.update_status = AsyncMock()
        MockCUDAO.return_value.list_by_run = AsyncMock(return_value=[big_unit, tiny_unit])

        await review_run(run_id, mock_db, mock_provider, concurrency=1, repo_dir=tmp_path)

    mock_reviewer.review_all.assert_not_called()
