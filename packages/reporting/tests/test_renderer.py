from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from devmanager_reporting.renderer import render_markdown

# ── Fake data helpers ─────────────────────────────────────────────────────────


@dataclass
class FakeRun:
    run_id: uuid.UUID = field(default_factory=uuid.uuid4)
    target_branch: str = "main"
    target_sha: str = "abc1234567890"
    baseline_sha: str = "def0987654321"
    started_at: datetime = field(default_factory=lambda: datetime(2026, 6, 7, 10, 0, 0, tzinfo=UTC))
    completed_at: datetime | None = None


@dataclass
class FakeScore:
    score_id: uuid.UUID = field(default_factory=uuid.uuid4)
    final_score: float = 85.0
    grade: str = "B"
    confidence: float = 0.847
    scoring_version: str = "v1"
    deductions: list = field(
        default_factory=lambda: [
            {
                "severity": "high",
                "confidence": 1.0,
                "base_deduction": 10.0,
                "actual_deduction": 10.0,
                "capped_deduction": 10.0,
                "category": "security",
            },
        ]
    )
    caps: list = field(default_factory=list)
    limitations: list = field(default_factory=list)


@dataclass
class FakeFinding:
    finding_id: str = "F-20260607-001"
    category: str = "security"
    severity: str = "high"
    confidence: float = 1.0
    file_path: str = "src/auth.py"
    start_line: int = 42
    end_line: int = 55
    observation: str = "SQL injection in user input"
    impact: str = "Auth bypass"
    recommendation: str = "Use parameterized queries"
    verification: str = "Add integration test"
    evidence_refs: list = field(default_factory=lambda: ["diff:src/auth.py:42-55"])


@dataclass
class FakeUnit:
    file_path: str = "src/auth.py"
    change_type: str = "modified"
    added_lines: int = 20
    deleted_lines: int = 5
    owner: str | None = None
    is_binary: bool = False
    is_generated: bool = False
    is_vendor: bool = False


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_render_contains_repo_name():
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/my-repo",
        score=None,
        findings=[],
        change_units=[],
    )
    assert "org/my-repo" in md


def test_render_contains_score_and_grade():
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=FakeScore(final_score=85.0, grade="B"),
        findings=[],
        change_units=[],
    )
    assert "85.0" in md
    assert "Grade: B" in md


def test_render_no_score_shows_placeholder():
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=None,
        findings=[],
        change_units=[],
    )
    assert "Not yet scored" in md


def test_render_empty_findings_shows_celebration():
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=FakeScore(),
        findings=[],
        change_units=[],
    )
    assert "No findings" in md


def test_render_finding_appears():
    finding = FakeFinding()
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=FakeScore(),
        findings=[finding],
        change_units=[],
    )
    assert "F-20260607-001" in md
    assert "SQL injection in user input" in md
    assert "src/auth.py" in md
    assert "Auth bypass" in md
    assert "Use parameterized queries" in md


def test_render_change_summary():
    units = [
        FakeUnit("src/a.py", added_lines=10, deleted_lines=3),
        FakeUnit("src/b.py", added_lines=5, deleted_lines=1),
    ]
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=None,
        findings=[],
        change_units=units,
    )
    assert "Files changed" in md
    assert "2" in md  # 2 files


def test_render_binary_files_counted_separately():
    units = [
        FakeUnit("image.png", is_binary=True),
        FakeUnit("src/main.py"),
    ]
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=None,
        findings=[],
        change_units=units,
    )
    assert "Binary files" in md
    assert "1" in md


def test_render_category_caps_shown():
    score = FakeScore(caps=["security capped at 35 pts (raw=100.00)"])
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=score,
        findings=[],
        change_units=[],
    )
    assert "Category Caps Applied" in md
    assert "security capped" in md


def test_render_target_sha_in_header():
    run = FakeRun(target_sha="deadbeefcafe1234")
    md = render_markdown(
        run=run,
        repository_full_name="org/repo",
        score=None,
        findings=[],
        change_units=[],
    )
    assert "deadbeef" in md  # first 8 chars


def test_render_footer_present():
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=None,
        findings=[],
        change_units=[],
    )
    assert "DevManager" in md
    assert "shadow/read-only" in md


def test_render_findings_sorted_by_severity():
    findings = [
        FakeFinding(finding_id="F-001", severity="low"),
        FakeFinding(finding_id="F-002", severity="critical"),
        FakeFinding(finding_id="F-003", severity="medium"),
    ]
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=None,
        findings=findings,
        change_units=[],
    )
    idx_critical = md.index("F-002")
    idx_medium = md.index("F-003")
    idx_low = md.index("F-001")
    assert idx_critical < idx_medium < idx_low


def test_render_multiple_findings_count():
    findings = [FakeFinding(finding_id=f"F-{i:03d}") for i in range(5)]
    md = render_markdown(
        run=FakeRun(),
        repository_full_name="org/repo",
        score=None,
        findings=findings,
        change_units=[],
    )
    assert "5 total" in md
