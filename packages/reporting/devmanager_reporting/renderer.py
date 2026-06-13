from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "informational"]
_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "informational": "⚪",
}
_APP_VERSION = "0.1.0"


def _ts(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _short(sha: str | None, n: int = 8) -> str:
    return (sha or "")[:n] or "—"


def _grade_badge(grade: str | None) -> str:
    badges = {"A": "✅", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"}
    return badges.get(grade or "", "")


def render_markdown(
    *,
    run: Any,
    repository_full_name: str,
    score: Any | None,
    findings: list[Any],
    change_units: list[Any],
) -> str:
    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        "# DevManager Code Review Report",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Repository** | `{repository_full_name}` |",
        f"| **Branch** | `{getattr(run, 'target_branch', '—')}` |",
        f"| **Target SHA** | `{_short(getattr(run, 'target_sha', None))}` |",
        f"| **Baseline SHA** | `{_short(getattr(run, 'baseline_sha', None))}` |",
        f"| **Run ID** | `{run.run_id}` |",
        f"| **Started** | {_ts(getattr(run, 'started_at', None))} |",
        f"| **Completed** | {_ts(getattr(run, 'completed_at', None))} |",
        "",
        "---",
        "",
    ]

    # ── Score ─────────────────────────────────────────────────────────────────
    if score is not None:
        fs = float(score.final_score) if score.final_score is not None else 0.0
        grade = score.grade or "?"
        conf = float(score.confidence) if score.confidence is not None else 0.0
        badge = _grade_badge(grade)
        lines += [
            f"## Score: {fs:.1f} / 100  (Grade: {grade} {badge})",
            "",
            f"> Confidence: {conf:.3f} | Scoring version: `{score.scoring_version}`",
            "",
        ]

        # Severity breakdown
        sev_counts: Counter[str] = Counter()
        sev_deductions: dict[str, float] = {}
        for d in score.deductions or []:
            sev = d.get("severity", "unknown")
            sev_counts[sev] += 1
            actual = d.get("actual_deduction", 0.0)
            capped = d.get("capped_deduction", actual)
            sev_deductions[sev] = sev_deductions.get(sev, 0.0) + capped

        if sev_counts:
            lines += [
                "| Severity | Count | Deducted pts |",
                "|----------|------:|-------------:|",
            ]
            for sev in _SEVERITY_ORDER:
                if sev in sev_counts:
                    emoji = _SEVERITY_EMOJI.get(sev, "")
                    count = sev_counts[sev]
                    deducted = sev_deductions.get(sev, 0.0)
                    lines.append(f"| {emoji} {sev.capitalize()} | {count} | {deducted:.2f} |")
            lines.append("")

        if score.caps:
            lines += ["### Category Caps Applied", ""]
            for cap in score.caps:
                lines.append(f"- {cap}")
            lines.append("")

        if score.limitations:
            lines += ["### Limitations", ""]
            for lim in score.limitations:
                lines.append(f"- {lim}")
            lines.append("")
    else:
        lines += ["## Score", "", "> Not yet scored.", "", "---", ""]

    lines += ["---", ""]

    # ── Findings ─────────────────────────────────────────────────────────────
    total = len(findings)
    lines += [f"## Findings ({total} total)", ""]

    if not findings:
        lines += ["> No findings. 🎉", ""]
    else:
        sorted_findings = sorted(
            findings,
            key=lambda f: (
                _SEVERITY_ORDER.index(getattr(f, "severity", "informational").lower())
                if getattr(f, "severity", "informational").lower() in _SEVERITY_ORDER
                else 99,
                getattr(f, "category", ""),
            ),
        )

        for f in sorted_findings:
            fid = getattr(f, "finding_id", "?")
            sev = getattr(f, "severity", "?")
            cat = getattr(f, "category", "?")
            fp = getattr(f, "file_path", "?")
            sl = getattr(f, "start_line", "?")
            el = getattr(f, "end_line", sl)
            emoji = _SEVERITY_EMOJI.get(sev.lower(), "")
            conf = float(getattr(f, "confidence", 0.0))

            lines += [
                f"### [{fid}] {emoji} {sev.capitalize()} — {cat}",
                "",
                f"**File**: `{fp}:{sl}–{el}`  |  **Confidence**: {conf:.0%}",
                "",
                f"**Observation**: {getattr(f, 'observation', '')}",
                "",
                f"**Impact**: {getattr(f, 'impact', '')}",
                "",
                f"**Recommendation**: {getattr(f, 'recommendation', '')}",
                "",
                f"**Verification**: {getattr(f, 'verification', '')}",
                "",
            ]
            evidence = getattr(f, "evidence_refs", []) or []
            if evidence:
                lines.append(f"**Evidence**: {', '.join(str(e) for e in evidence)}")
                lines.append("")
            lines.append("---")
            lines.append("")

    # ── Change Summary ────────────────────────────────────────────────────────
    total_files = len(change_units)
    total_added = sum(getattr(u, "added_lines", 0) for u in change_units)
    total_deleted = sum(getattr(u, "deleted_lines", 0) for u in change_units)
    reviewable = sum(
        1
        for u in change_units
        if not getattr(u, "is_binary", False)
        and not getattr(u, "is_generated", False)
        and not getattr(u, "is_vendor", False)
    )
    binary_count = sum(1 for u in change_units if getattr(u, "is_binary", False))
    generated_count = sum(1 for u in change_units if getattr(u, "is_generated", False))

    lines += [
        "## Change Summary",
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Files changed | {total_files} |",
        f"| Lines added | {total_added:,} |",
        f"| Lines deleted | {total_deleted:,} |",
        f"| Reviewable files | {reviewable} |",
        f"| Binary files (skipped) | {binary_count} |",
        f"| Generated files (skipped) | {generated_count} |",
        "",
        "---",
        "",
    ]

    # ── File list ─────────────────────────────────────────────────────────────
    if change_units:
        lines += ["## Files Changed", ""]
        lines += [
            "| File | Type | +Lines | −Lines | Owner |",
            "|------|------|-------:|-------:|-------|",
        ]
        for u in sorted(change_units, key=lambda x: getattr(x, "file_path", "")):
            fp = getattr(u, "file_path", "")
            ct = getattr(u, "change_type", "")
            added = getattr(u, "added_lines", 0)
            deleted = getattr(u, "deleted_lines", 0)
            owner = getattr(u, "owner", None) or "—"
            flag = ""
            if getattr(u, "is_binary", False):
                flag = " _(binary)_"
            elif getattr(u, "is_generated", False):
                flag = " _(generated)_"
            elif getattr(u, "is_vendor", False):
                flag = " _(vendor)_"
            lines.append(f"| `{fp}`{flag} | {ct} | +{added} | −{deleted} | {owner} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Footer ────────────────────────────────────────────────────────────────
    generated_at = _ts(datetime.now(UTC))
    lines += [
        (
            f"*Report generated by DevManager v{_APP_VERSION} "
            f"(shadow/read-only mode) — {generated_at}*"
        ),
    ]

    return "\n".join(lines)
