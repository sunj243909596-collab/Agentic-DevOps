from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    pass

# ── Constants ─────────────────────────────────────────────────────────────────

_BASE_DEDUCTIONS: dict[str, float] = {
    "critical": 25.0,
    "high": 10.0,
    "medium": 5.0,
    "low": 2.0,
    "informational": 0.5,
}

_CATEGORY_CAP = 35.0  # max points deducted per category

_GRADE_THRESHOLDS = [
    (90.0, "A"),
    (75.0, "B"),
    (60.0, "C"),
    (40.0, "D"),
]


# ── Protocol for Finding inputs (accepts DB model or plain dict) ──────────────

class FindingLike(Protocol):
    @property
    def finding_id(self) -> str: ...
    @property
    def category(self) -> str: ...
    @property
    def severity(self) -> str: ...
    @property
    def confidence(self) -> float: ...
    @property
    def dedupe_key(self) -> str | None: ...


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ScoreResult:
    final_score: float
    grade: str
    confidence: float
    deductions: list[dict[str, Any]]
    caps: list[str]
    limitations: list[str]

    def as_db_kwargs(self) -> dict[str, Any]:
        return {
            "final_score": self.final_score,
            "grade": self.grade,
            "confidence": self.confidence,
            "deductions": self.deductions,
            "caps": self.caps,
            "limitations": self.limitations,
        }


# ── Engine ────────────────────────────────────────────────────────────────────

def _grade(score: float) -> str:
    for threshold, letter in _GRADE_THRESHOLDS:
        if score >= threshold:
            return letter
    return "F"


def compute_score(findings: list[Any]) -> ScoreResult:
    """
    Deterministic scoring engine.  Agent-generated findings are inputs only;
    the final score is computed entirely by this function.

    Algorithm:
      1. Deduplicate by dedupe_key (keep first occurrence).
      2. For each unique finding: actual_deduction = base × confidence.
      3. Sum deductions per category; cap each at _CATEGORY_CAP.
      4. final_score = max(0, 100 - total_deductions), rounded to 2 dp.
      5. Overall confidence = weighted average (weight = base_deduction).
    """
    if not findings:
        return ScoreResult(
            final_score=100.0,
            grade="A",
            confidence=1.0,
            deductions=[],
            caps=[],
            limitations=["No findings — perfect score by default."],
        )

    # Step 1: deduplicate
    seen_keys: set[str] = set()
    unique: list[Any] = []
    dupes = 0
    for f in findings:
        key = getattr(f, "dedupe_key", None) or getattr(f, "finding_id", None) or id(f)
        if key in seen_keys:
            dupes += 1
            continue
        seen_keys.add(key)
        unique.append(f)

    # Step 2: compute per-finding deductions grouped by category
    category_details: dict[str, list[dict[str, Any]]] = {}
    confidence_numerator = 0.0
    confidence_denominator = 0.0

    for f in unique:
        sev = getattr(f, "severity", "informational").lower()
        base = _BASE_DEDUCTIONS.get(sev, 0.5)
        conf = float(getattr(f, "confidence", 0.7))
        conf = max(0.0, min(1.0, conf))
        actual = round(base * conf, 4)

        cat = getattr(f, "category", "unknown").lower()
        category_details.setdefault(cat, []).append(
            {
                "finding_id": getattr(f, "finding_id", ""),
                "category": cat,
                "severity": sev,
                "confidence": conf,
                "base_deduction": base,
                "actual_deduction": actual,
            }
        )
        confidence_numerator += conf * base
        confidence_denominator += base

    # Step 3: apply per-category cap
    all_deduction_rows: list[dict[str, Any]] = []
    caps: list[str] = []
    total_deduction = 0.0

    for cat, rows in sorted(category_details.items()):
        cat_total = sum(r["actual_deduction"] for r in rows)
        if cat_total > _CATEGORY_CAP:
            ratio = _CATEGORY_CAP / cat_total
            for r in rows:
                r["capped_deduction"] = round(r["actual_deduction"] * ratio, 4)
            caps.append(f"{cat} capped at {_CATEGORY_CAP:.0f} pts (raw={cat_total:.2f})")
            cat_total = _CATEGORY_CAP
        else:
            for r in rows:
                r["capped_deduction"] = r["actual_deduction"]
        total_deduction += cat_total
        all_deduction_rows.extend(rows)

    # Step 4: final score
    final_score = round(max(0.0, 100.0 - total_deduction), 2)

    # Step 5: overall confidence
    overall_confidence = (
        round(confidence_numerator / confidence_denominator, 3)
        if confidence_denominator > 0
        else 1.0
    )

    # Limitations
    limitations: list[str] = []
    if dupes > 0:
        limitations.append(f"{dupes} duplicate finding(s) removed before scoring.")

    return ScoreResult(
        final_score=final_score,
        grade=_grade(final_score),
        confidence=overall_confidence,
        deductions=all_deduction_rows,
        caps=caps,
        limitations=limitations,
    )
