from __future__ import annotations

from dataclasses import dataclass

from devmanager_scoring.engine import _grade, compute_score

# ── Helpers ───────────────────────────────────────────────────────────────────


@dataclass
class FakeFinding:
    finding_id: str
    category: str
    severity: str
    confidence: float
    dedupe_key: str | None = None


def make_finding(
    finding_id: str = "F-20260607-001",
    category: str = "correctness",
    severity: str = "medium",
    confidence: float = 1.0,
    dedupe_key: str | None = None,
) -> FakeFinding:
    return FakeFinding(
        finding_id=finding_id,
        category=category,
        severity=severity,
        confidence=confidence,
        dedupe_key=dedupe_key or finding_id,
    )


# ── _grade ────────────────────────────────────────────────────────────────────


def test_grade_boundaries():
    assert _grade(100.0) == "A"
    assert _grade(90.0) == "A"
    assert _grade(89.9) == "B"
    assert _grade(75.0) == "B"
    assert _grade(74.9) == "C"
    assert _grade(60.0) == "C"
    assert _grade(59.9) == "D"
    assert _grade(40.0) == "D"
    assert _grade(39.9) == "F"
    assert _grade(0.0) == "F"


# ── compute_score — empty ─────────────────────────────────────────────────────


def test_empty_findings_perfect_score():
    result = compute_score([])
    assert result.final_score == 100.0
    assert result.grade == "A"
    assert result.confidence == 1.0
    assert result.deductions == []
    assert result.caps == []


# ── compute_score — deduction math ────────────────────────────────────────────


def test_single_medium_full_confidence():
    # medium(5) × confidence(1.0) = 5.0 deducted → score = 95
    result = compute_score([make_finding(severity="medium", confidence=1.0)])
    assert result.final_score == 95.0
    assert result.grade == "A"


def test_single_critical_half_confidence():
    # critical(25) × 0.5 = 12.5 deducted → score = 87.5
    result = compute_score([make_finding(severity="critical", confidence=0.5)])
    assert result.final_score == 87.5
    assert result.grade == "B"


def test_informational_deduction():
    # informational(0.5) × 1.0 = 0.5 → score = 99.5
    result = compute_score([make_finding(severity="informational", confidence=1.0)])
    assert result.final_score == 99.5


def test_multiple_findings_accumulate():
    findings = [
        make_finding("F-001", "security", "high", 1.0),  # −10
        make_finding("F-002", "security", "medium", 1.0),  # −5
        make_finding("F-003", "correctness", "low", 1.0),  # −2
    ]
    result = compute_score(findings)
    assert result.final_score == 83.0


def test_score_floors_at_zero():
    # 4 categories × 4 criticals each → 4 × 35 cap = 140 deducted → floor at 0
    categories = ["security", "correctness", "testing", "performance"]
    findings = [
        make_finding(f"F-{cat}-{i}", cat, "critical", 1.0, dedupe_key=f"{cat}-key-{i}")
        for cat in categories
        for i in range(4)
    ]
    result = compute_score(findings)
    assert result.final_score == 0.0
    assert result.grade == "F"


# ── compute_score — category cap ─────────────────────────────────────────────


def test_category_cap_applied():
    # 4 critical in one category = 100 raw, capped at 35
    findings = [
        make_finding(f"F-{i}", "security", "critical", 1.0, dedupe_key=f"cap-{i}") for i in range(4)
    ]
    result = compute_score(findings)
    assert result.final_score == 65.0  # 100 - 35
    assert any("security" in c for c in result.caps)


def test_two_categories_both_capped():
    # 4 criticals in security + 4 criticals in correctness → 2 × 35 = 70 deducted → score = 30
    findings = [
        make_finding(f"F-s{i}", "security", "critical", 1.0, dedupe_key=f"sec-{i}")
        for i in range(4)
    ] + [
        make_finding(f"F-c{i}", "correctness", "critical", 1.0, dedupe_key=f"cor-{i}")
        for i in range(4)
    ]
    result = compute_score(findings)
    assert result.final_score == 30.0
    assert len(result.caps) == 2


def test_category_cap_not_triggered_below_threshold():
    # 3 medium in one category = 15 < 35 → no cap
    findings = [
        make_finding(f"F-{i}", "testing", "medium", 1.0, dedupe_key=f"t-{i}") for i in range(3)
    ]
    result = compute_score(findings)
    assert result.final_score == 85.0
    assert result.caps == []


# ── compute_score — deduplication ────────────────────────────────────────────


def test_duplicate_findings_counted_once():
    # Same dedupe_key → only first is counted
    findings = [
        make_finding("F-001", "security", "high", 1.0, dedupe_key="same-key"),
        make_finding("F-002", "security", "high", 1.0, dedupe_key="same-key"),
    ]
    result = compute_score(findings)
    assert result.final_score == 90.0  # −10 once
    assert "1 duplicate" in result.limitations[0]


def test_different_dedupe_keys_both_counted():
    findings = [
        make_finding("F-001", "security", "high", 1.0, dedupe_key="key-a"),
        make_finding("F-002", "security", "high", 1.0, dedupe_key="key-b"),
    ]
    result = compute_score(findings)
    assert result.final_score == 80.0  # −10 twice


# ── compute_score — confidence weighting ─────────────────────────────────────


def test_overall_confidence_weighted_by_base():
    # one high(10) conf=0.8, one medium(5) conf=0.6
    # weighted avg = (0.8×10 + 0.6×5) / (10+5) = (8+3)/15 = 0.733...
    findings = [
        make_finding("F-001", "security", "high", 0.8),
        make_finding("F-002", "correctness", "medium", 0.6),
    ]
    result = compute_score(findings)
    expected = round((0.8 * 10 + 0.6 * 5) / 15, 3)
    assert result.confidence == expected


# ── ScoreResult.as_db_kwargs ──────────────────────────────────────────────────


def test_as_db_kwargs_keys():
    result = compute_score([make_finding()])
    kwargs = result.as_db_kwargs()
    assert set(kwargs.keys()) == {
        "final_score",
        "grade",
        "confidence",
        "deductions",
        "caps",
        "limitations",
    }
