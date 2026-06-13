"""
M8 Shadow Pilot — End-to-End Pipeline Integration Test
=======================================================
Validates the full read-only pipeline:

  real git repo  →  diff extraction  →  hunk extraction
                 →  scoring engine   →  markdown renderer

No database, no LLM calls. All git operations are real subprocess calls.
Findings are hand-crafted to represent a realistic review output.
"""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from devmanager_git.differ import parse_diff
from devmanager_git.fetcher import (
    _EMPTY_TREE,
    get_diff_name_status,
    get_diff_numstat,
)
from devmanager_git.hunks import extract_all_hunks
from devmanager_reporting.renderer import render_markdown
from devmanager_scoring.engine import compute_score

# ── Git fixture ───────────────────────────────────────────────────────────────


@pytest.fixture
def rich_git_repo(tmp_path: Path):
    """
    Creates a bare git repo with a realistic Python project:
      commit-1 (baseline): initial module with a known bug
      commit-2 (target):   patch commit that changes multiple files
    """
    work = tmp_path / "work"
    work.mkdir()

    def git(*args):
        subprocess.run(["git", *args], cwd=work, capture_output=True, check=True)

    def sha():
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=work, capture_output=True, text=True
        ).stdout.strip()

    git("init")
    git("config", "user.email", "pilot@devmanager.test")
    git("config", "user.name", "Pilot")

    # Baseline commit: auth module with SQL injection bug + test file
    (work / "src").mkdir()
    (work / "src" / "__init__.py").write_text("")
    (work / "src" / "auth.py").write_text(
        "def login(username, password):\n"
        '    query = "SELECT * FROM users WHERE name=\'"'
        ' + username + "\' AND pass=\'" + password + "\'"\n'
        "    return db.execute(query)\n"
    )
    (work / "src" / "utils.py").write_text(
        "def divide(a, b):\n    return a / b  # may raise ZeroDivisionError\n"
    )
    (work / "tests").mkdir()
    (work / "tests" / "test_auth.py").write_text("def test_login_placeholder():\n    pass\n")
    git("add", ".")
    git("commit", "-m", "initial: auth module with login")
    baseline_sha = sha()

    # Target commit: patch auth.py, add docstring to utils, update test
    (work / "src" / "auth.py").write_text(
        "import hashlib\n"
        "\n"
        "def login(username: str, password: str) -> dict | None:\n"
        '    """Authenticate user with parameterized query."""\n'
        '    query = "SELECT * FROM users WHERE name=? AND pass=?"\n'
        "    return db.execute(query, (username, hashlib.sha256(password.encode()).hexdigest()))\n"
    )
    (work / "src" / "utils.py").write_text(
        "def divide(a: float, b: float) -> float:\n"
        '    """Safe division with zero check."""\n'
        "    if b == 0:\n"
        '        raise ValueError("division by zero")\n'
        "    return a / b\n"
    )
    (work / "tests" / "test_auth.py").write_text(
        "from src.auth import login\n"
        "\n"
        "def test_login_returns_none_for_unknown():\n"
        '    assert login("nobody", "wrong") is None\n'
        "\n"
        "def test_login_sql_injection_rejected():\n"
        "    # should not raise or return data\n"
        '    result = login("admin\' OR 1=1 --", "x")\n'
        "    assert result is None\n"
    )
    git("add", ".")
    git("commit", "-m", "fix: use parameterized query and safe division")
    target_sha = sha()

    bare = tmp_path / "repo.git"
    subprocess.run(
        ["git", "clone", "--mirror", str(work), str(bare)],
        capture_output=True,
        check=True,
    )
    return {"bare": bare, "baseline": baseline_sha, "target": target_sha}


# ── Fake domain objects for rendering ─────────────────────────────────────────


@dataclass
class FakeRun:
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    target_branch: str = "main"
    target_sha: str = "abc1234"
    baseline_sha: str = "def5678"
    started_at: datetime = field(default_factory=lambda: datetime(2026, 6, 7, 10, 0, tzinfo=UTC))
    completed_at: datetime = field(default_factory=lambda: datetime(2026, 6, 7, 10, 5, tzinfo=UTC))


@dataclass
class FakeScore:
    score_id: uuid.UUID = field(default_factory=uuid.uuid4)
    final_score: float = 90.0
    grade: str = "A"
    confidence: float = 0.9
    scoring_version: str = "v1"
    deductions: list = field(default_factory=list)
    caps: list = field(default_factory=list)
    limitations: list = field(default_factory=list)


@dataclass
class FakeFinding:
    finding_id: str
    category: str
    severity: str
    confidence: float
    file_path: str
    start_line: int
    end_line: int
    observation: str
    impact: str
    recommendation: str
    verification: str
    evidence_refs: list
    dedupe_key: str = ""


@dataclass
class FakeCU:
    """Wraps a ChangeUnit dict as an attribute-based object."""

    file_path: str
    change_type: str
    added_lines: int
    deleted_lines: int
    owner: str | None = None
    is_binary: bool = False
    is_generated: bool = False
    is_vendor: bool = False
    is_test_file: bool = False


def _cu_from_dict(d: dict) -> FakeCU:
    return FakeCU(
        file_path=d["file_path"],
        change_type=d["change_type"],
        added_lines=d.get("added_lines", 0),
        deleted_lines=d.get("deleted_lines", 0),
        is_binary=d.get("is_binary", False),
        is_generated=d.get("is_generated", False),
        is_vendor=d.get("is_vendor", False),
        is_test_file=d.get("is_test_file", False),
    )


# ── Phase helpers ─────────────────────────────────────────────────────────────


def _make_realistic_findings(
    run_id: uuid.UUID, units: list[dict], target_sha: str
) -> list[FakeFinding]:
    """
    Returns a hand-crafted set of findings that a real agent might produce
    for the rich_git_repo diff.
    """
    return [
        FakeFinding(
            finding_id="F-20260607-001",
            category="security",
            severity="high",
            confidence=0.95,
            file_path="src/auth.py",
            start_line=2,
            end_line=3,
            observation=(
                "Previous implementation used string interpolation in SQL query "
                "(f-string), creating SQL injection vulnerability. The fix uses "
                "parameterized queries correctly."
            ),
            impact=(
                "SQL injection could allow attackers to bypass authentication "
                "or exfiltrate the entire users table."
            ),
            recommendation=(
                "The patch is correct. Ensure all database calls throughout the "
                "codebase use parameterized queries — audit other files."
            ),
            verification=(
                "Add integration tests with malicious input payloads (e.g., "
                '"admin\' OR 1=1 --") and verify they are rejected.'
            ),
            evidence_refs=["diff:src/auth.py:2-3"],
            dedupe_key="pilot-finding-001",
        ),
        FakeFinding(
            finding_id="F-20260607-002",
            category="correctness",
            severity="medium",
            confidence=0.8,
            file_path="src/utils.py",
            start_line=3,
            end_line=4,
            observation=(
                "ZeroDivisionError was unhandled before this patch. "
                "The fix adds an explicit guard with a descriptive error."
            ),
            impact=(
                "Callers would receive an unhandled ZeroDivisionError at runtime "
                "with no actionable message."
            ),
            recommendation=(
                "Good fix. Consider returning 0 or infinity depending on context, "
                "or document that ValueError is the expected contract."
            ),
            verification=(
                "Unit test: assert divide(1, 0) raises ValueError with message 'division by zero'."
            ),
            evidence_refs=["diff:src/utils.py:3-4"],
            dedupe_key="pilot-finding-002",
        ),
        FakeFinding(
            finding_id="F-20260607-003",
            category="testing",
            severity="low",
            confidence=0.7,
            file_path="tests/test_auth.py",
            start_line=6,
            end_line=8,
            observation=(
                "SQL injection test uses a hardcoded payload but does not cover "
                "other injection patterns (UNION-based, time-based blind)."
            ),
            impact=(
                "Partial test coverage — a more sophisticated injection could "
                "still succeed if the parameterization has edge cases."
            ),
            recommendation=(
                "Expand the injection test suite using a fuzzing approach "
                "or a library like sqlmap's input corpus."
            ),
            verification=(
                "Run the test with at least 5 distinct injection payloads and "
                "verify all are rejected."
            ),
            evidence_refs=["diff:tests/test_auth.py:6-8"],
            dedupe_key="pilot-finding-003",
        ),
    ]


# ── E2E test: git → diff → score → report ────────────────────────────────────


@pytest.mark.asyncio
async def test_diff_extraction(rich_git_repo: dict):
    """Phase 1-3: real git diff gives expected file list."""
    repo_dir = rich_git_repo["bare"]
    baseline = rich_git_repo["baseline"]
    target = rich_git_repo["target"]

    numstat = await get_diff_numstat(repo_dir, baseline, target)
    name_status = await get_diff_name_status(repo_dir, baseline, target)

    run_id = uuid.uuid4()
    units = parse_diff(numstat, name_status, run_id, "test/pilot-repo", baseline, target)

    file_paths = {u["file_path"] for u in units}
    assert "src/auth.py" in file_paths
    assert "src/utils.py" in file_paths
    assert "tests/test_auth.py" in file_paths
    assert len(units) == 3


@pytest.mark.asyncio
async def test_hunk_extraction(tmp_path: Path, rich_git_repo: dict):
    """Phase 4: hunk files are written for source files."""
    repo_dir = rich_git_repo["bare"]
    baseline = rich_git_repo["baseline"]
    target = rich_git_repo["target"]

    numstat = await get_diff_numstat(repo_dir, baseline, target)
    name_status = await get_diff_name_status(repo_dir, baseline, target)
    run_id = uuid.uuid4()
    units = parse_diff(numstat, name_status, run_id, "test/pilot-repo", baseline, target)

    hunks_dir = tmp_path / "hunks"
    hunks_map = await extract_all_hunks(repo_dir, baseline, target, units, hunks_dir)

    # All 3 source files should have hunks
    cu_to_path = {str(u["change_unit_id"]): u["file_path"] for u in units}
    for cu_id, ref in hunks_map.items():
        assert ref.startswith("file://")
        hunk_file = Path(ref.removeprefix("file://"))
        assert hunk_file.exists()
        content = hunk_file.read_text()
        assert "@@" in content, f"Missing diff header in hunk for {cu_to_path.get(cu_id)}"


@pytest.mark.asyncio
async def test_scoring_from_pilot_findings(rich_git_repo: dict):
    """Phase 5-6: findings from pilot repo produce expected score."""
    run_id = uuid.uuid4()
    findings = _make_realistic_findings(run_id, [], rich_git_repo["target"])

    result = compute_score(findings)

    # high(10)×0.95 + medium(5)×0.8 + low(2)×0.7 = 9.5 + 4.0 + 1.4 = 14.9
    assert result.final_score == pytest.approx(85.1, abs=0.1)
    assert result.grade == "B"
    assert result.confidence > 0
    assert len(result.deductions) == 3
    assert result.caps == []


@pytest.mark.asyncio
async def test_full_pipeline_git_to_report(tmp_path: Path, rich_git_repo: dict):
    """
    Full shadow-pilot chain:
      real git diff  →  ChangeUnit dicts  →  hunk files
      mock findings  →  compute_score()   →  render_markdown()
      asserts the final Markdown report is coherent and complete.
    """
    repo_dir = rich_git_repo["bare"]
    baseline = rich_git_repo["baseline"]
    target = rich_git_repo["target"]
    run_id = uuid.uuid4()

    # Phase 1-3: extract diff
    numstat = await get_diff_numstat(repo_dir, baseline, target)
    name_status = await get_diff_name_status(repo_dir, baseline, target)
    units = parse_diff(numstat, name_status, run_id, "test/pilot-repo", baseline, target)
    assert units, "Diff extraction yielded no change units"

    # Phase 4: extract hunks
    hunks_dir = tmp_path / "hunks"
    hunks_map = await extract_all_hunks(repo_dir, baseline, target, units, hunks_dir)
    assert hunks_map, "No hunks extracted"

    # Verify hunk content is diff-shaped
    for ref in hunks_map.values():
        content = Path(ref.removeprefix("file://")).read_text()
        assert "@@" in content

    # Phase 5: construct pilot findings (simulating agent output)
    findings = _make_realistic_findings(run_id, units, target)

    # Phase 6: deterministic scoring
    score_result = compute_score(findings)
    assert 0.0 <= score_result.final_score <= 100.0

    # Materialise a fake score object for the renderer
    fake_score = FakeScore(
        final_score=score_result.final_score,
        grade=score_result.grade,
        confidence=score_result.confidence,
        deductions=score_result.deductions,
        caps=score_result.caps,
        limitations=score_result.limitations,
    )

    # Phase 7: render report
    fake_run = FakeRun(run_id=run_id, target_sha=target[:8], baseline_sha=baseline[:8])
    change_unit_objs = [_cu_from_dict(u) for u in units]

    markdown = render_markdown(
        run=fake_run,
        repository_full_name="test/pilot-repo",
        score=fake_score,
        findings=findings,
        change_units=change_unit_objs,
    )

    # Phase 8: assert report quality
    assert "# DevManager Code Review Report" in markdown
    assert "test/pilot-repo" in markdown
    assert "Grade:" in markdown
    assert str(score_result.grade) in markdown
    assert "src/auth.py" in markdown
    assert "src/utils.py" in markdown
    assert "tests/test_auth.py" in markdown
    assert "SQL injection" in markdown
    assert "F-20260607-001" in markdown
    assert "shadow/read-only" in markdown

    # Optionally write report to tmp_path for manual inspection
    report_file = tmp_path / "pilot_report.md"
    report_file.write_text(markdown, encoding="utf-8")
    assert report_file.stat().st_size > 500, "Report suspiciously small"


@pytest.mark.asyncio
async def test_pipeline_from_empty_tree(tmp_path: Path, rich_git_repo: dict):
    """
    Edge case: diff from the empty tree (first commit ever in a repo).
    Validates the empty-tree SHA is handled correctly.
    """
    repo_dir = rich_git_repo["bare"]
    target = rich_git_repo["baseline"]  # diff the first commit vs empty tree

    numstat = await get_diff_numstat(repo_dir, _EMPTY_TREE, target)
    name_status = await get_diff_name_status(repo_dir, _EMPTY_TREE, target)
    run_id = uuid.uuid4()
    units = parse_diff(numstat, name_status, run_id, "test/pilot-repo", _EMPTY_TREE, target)

    # The initial commit added src/auth.py, src/utils.py, tests/test_auth.py, src/__init__.py
    file_paths = {u["file_path"] for u in units}
    assert "src/auth.py" in file_paths
    assert all(u["change_type"] == "added" for u in units)

    # Scoring with no findings should give perfect score
    result = compute_score([])
    assert result.final_score == 100.0
    assert result.grade == "A"

    # Report renders without errors even with no findings
    markdown = render_markdown(
        run=FakeRun(),
        repository_full_name="test/pilot-repo",
        score=FakeScore(final_score=100.0, grade="A"),
        findings=[],
        change_units=[_cu_from_dict(u) for u in units],
    )
    assert "No findings" in markdown
    assert "100.0" in markdown
