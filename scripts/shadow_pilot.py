#!/usr/bin/env python3
"""
DevManager Shadow Pilot
=======================
Read-only trial run of the full analysis pipeline against a real repository.

Usage
-----
  uv run python scripts/shadow_pilot.py \\
      --clone-url  https://github.com/owner/repo.git \\
      --baseline   <from-sha-or-branch> \\
      --target     <to-sha-or-branch> \\
      [--output    report.md] \\
      [--workspace /tmp/devmanager/shadow] \\
      [--model     claude-opus-4-8]

Benchmark mode (N consecutive commits from --target, default HEAD):

  uv run python scripts/shadow_pilot.py \\
      --samples 10 \\
      [--clone-url  https://github.com/owner/repo.git] \\
      [--target     main] \\
      [--output    docs/perf-baseline.md]

Environment variables required for agent review (optional — review is skipped if absent):
  ANTHROPIC_API_KEY    or  ANTHROPIC_AUTH_TOKEN
  ANTHROPIC_BASE_URL   (optional; leave unset for official endpoint)
  ANTHROPIC_MODEL      (default: claude-opus-4-8)

What this script does (read-only, no DB writes):
  1. Clone / fetch the repository into a local bare mirror
  2. Resolve merge-base between baseline and target SHAs
  3. Extract the diff: numstat + name-status + per-file hunks
  4. (If API key present) Run AgentReviewer (single agent + 9 skills)
  5. Score the findings deterministically
  6. Render a Markdown report
  7. Print the report to stdout (and optionally save to --output)

Nothing is written to the database; no external services are called beyond
the git host and (optionally) the LLM endpoint.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import statistics
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("shadow_pilot")


# ── Lazy imports of workspace packages ───────────────────────────────────────


def _import_packages():
    """Ensure the workspace packages are importable when run via uv run."""
    here = Path(__file__).parent.parent
    sys.path.insert(0, str(here / "packages" / "git"))
    sys.path.insert(0, str(here / "packages" / "llm"))
    sys.path.insert(0, str(here / "packages" / "scoring"))
    sys.path.insert(0, str(here / "packages" / "reporting"))
    sys.path.insert(0, str(here / "packages" / "agents"))
    sys.path.insert(0, str(here / "packages" / "domain" / "python"))


# ── Minimal fake domain objects (no DB needed) ───────────────────────────────


@dataclass
class _Run:
    run_id: uuid.UUID
    target_branch: str
    target_sha: str
    baseline_sha: str
    started_at: datetime
    completed_at: datetime | None = None


@dataclass
class _Score:
    score_id: uuid.UUID = field(default_factory=uuid.uuid4)
    final_score: float = 100.0
    grade: str = "A"
    confidence: float = 1.0
    scoring_version: str = "v1"
    deductions: list = field(default_factory=list)
    caps: list = field(default_factory=list)
    limitations: list = field(default_factory=list)


@dataclass
class _Finding:
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
class _ChangeUnit:
    file_path: str
    change_type: str
    added_lines: int
    deleted_lines: int
    language: str
    hunks_ref: str | None = None
    owner: str | None = None
    is_binary: bool = False
    is_generated: bool = False
    is_vendor: bool = False
    is_test_file: bool = False
    risk_tags: list = field(default_factory=list)
    repository_full_name: str = ""
    change_unit_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class SampleMetrics:
    baseline_sha: str
    target_sha: str
    files_changed: int
    reviewable_files: int
    agent_latency_s: float
    findings: int
    input_tokens: int
    output_tokens: int
    llm_calls: int
    provider: str


class _MetricsProvider:
    """Wrap an LLMProvider to accumulate token / call counts."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name = getattr(inner, "name", "wrapped")
        self.input_tokens = 0
        self.output_tokens = 0
        self.llm_calls = 0

    async def complete(self, *, messages, **kwargs):
        self.llm_calls += 1
        resp = await self._inner.complete(messages=messages, **kwargs)
        usage = getattr(resp, "usage", None) or {}
        self.input_tokens += int(usage.get("input", 0))
        self.output_tokens += int(usage.get("output", 0))
        return resp


def _cu_from_dict(d: dict, hunks_map: dict) -> _ChangeUnit:
    cu_id = str(d.get("change_unit_id", ""))
    return _ChangeUnit(
        file_path=d["file_path"],
        change_type=d["change_type"],
        added_lines=d.get("added_lines", 0),
        deleted_lines=d.get("deleted_lines", 0),
        language=d.get("language", "unknown"),
        hunks_ref=hunks_map.get(cu_id),
        is_binary=d.get("is_binary", False),
        is_generated=d.get("is_generated", False),
        is_vendor=d.get("is_vendor", False),
        is_test_file=d.get("is_test_file", False),
        risk_tags=d.get("risk_tags", []),
        repository_full_name=d.get("repository_full_name", ""),
        change_unit_id=d.get("change_unit_id", uuid.uuid4()),
    )


# ── Agent review (optional) ───────────────────────────────────────────────────


async def _run_agent_review(
    units: list[_ChangeUnit],
    concurrency: int,
    *,
    force_mock: bool = False,
) -> tuple[list[dict], dict[str, Any]]:
    """Call AgentReviewer if API key is configured. Returns (findings, metrics)."""
    empty_metrics: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "llm_calls": 0,
        "provider": "skipped",
        "latency_s": 0.0,
    }
    try:
        from devmanager_agents.agent_reviewer import AgentReviewer
        from devmanager_agents.skills import default_registry
        from devmanager_llm import MockProvider, make_provider
    except ImportError as exc:
        log.warning("Could not import agent packages: %s — skipping agent review", exc)
        return [], empty_metrics

    api_key = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key and not force_mock:
        log.info(
            "No API key configured — skipping agent review "
            "(set ANTHROPIC_API_KEY or use --samples with auto-mock)"
        )
        return [], empty_metrics

    if force_mock or not api_key:
        provider = _MetricsProvider(MockProvider(model="mock-agent", scenario="agent"))
        provider_name = "mock(agent)"
    else:
        base_url = os.getenv("ANTHROPIC_BASE_URL") or None
        model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
        log.info("Agent review: model=%s  base_url=%s", model, base_url or "(official)")
        provider = _MetricsProvider(
            make_provider("claude", api_key=api_key, model=model, base_url=base_url)
        )
        provider_name = f"claude/{model}"

    reviewer = AgentReviewer(provider, default_registry(), max_iter=10)

    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []
    today = datetime.now(UTC).strftime("%Y%m%d")
    idx = 1

    reviewable = [u for u in units if not u.is_binary and not u.is_generated and not u.is_vendor]
    log.info("Reviewing %d files with AgentReviewer …", len(reviewable))

    t0 = time.perf_counter()

    async def _review_one(unit: _ChangeUnit):
        async with sem:
            try:
                return await reviewer.review_all(
                    [unit],
                    repo_dir=Path("/tmp"),
                )
            except Exception as exc:
                log.warning("Agent review on %s failed: %s", unit.file_path, exc)
                return []

    batches = await asyncio.gather(*[_review_one(u) for u in reviewable])

    latency_s = time.perf_counter() - t0

    for batch in batches:
        for f in batch:
            f["finding_id"] = f"F-{today}-{idx:03d}"
            idx += 1
            results.append(f)

    log.info("Agent review complete: %d raw findings in %.2fs", len(results), latency_s)
    metrics = {
        "input_tokens": provider.input_tokens,
        "output_tokens": provider.output_tokens,
        "llm_calls": provider.llm_calls,
        "provider": provider_name,
        "latency_s": latency_s,
    }
    return results, metrics


def _to_finding_objs(raw: list[dict]) -> list[_Finding]:
    out = []
    for f in raw:
        out.append(
            _Finding(
                finding_id=f.get("finding_id", "F-unknown"),
                category=f.get("category", "unknown"),
                severity=f.get("severity", "informational"),
                confidence=float(f.get("confidence", 0.7)),
                file_path=f.get("file", f.get("file_path", "unknown")),
                start_line=int(f.get("start_line", 1)),
                end_line=int(f.get("end_line", 1)),
                observation=f.get("observation", ""),
                impact=f.get("impact", ""),
                recommendation=f.get("recommendation", ""),
                verification=f.get("verification", ""),
                evidence_refs=f.get("evidence_refs", []),
                dedupe_key=f.get("dedupe_key", ""),
            )
        )
    return out


# ── Main pipeline ─────────────────────────────────────────────────────────────


async def run_shadow_pilot(
    clone_url: str,
    baseline: str,
    target: str,
    workspace: Path,
    output: Path | None,
    concurrency: int,
    repository_name: str | None,
) -> int:
    _import_packages()

    from devmanager_git.differ import parse_diff
    from devmanager_git.fetcher import (
        GitError,
        clone_or_fetch,
        detect_history_rewrite,
        get_diff_name_status,
        get_diff_numstat,
        resolve_merge_base,
    )
    from devmanager_git.hunks import extract_all_hunks
    from devmanager_reporting.renderer import render_markdown
    from devmanager_scoring.engine import compute_score

    run_id = uuid.uuid4()
    repo_name = repository_name or clone_url.rstrip("/").rstrip(".git").rsplit("/", 2)[-1]
    if "/" not in repo_name:
        repo_name = f"shadow/{repo_name}"

    workspace.mkdir(parents=True, exist_ok=True)
    repo_dir = workspace / "repo.git"
    hunks_dir = workspace / "hunks" / str(run_id)

    started_at = datetime.now(UTC)
    log.info("=== DevManager Shadow Pilot ===")
    log.info("Repository : %s", repo_name)
    log.info("Clone URL  : %s", clone_url)
    log.info("Baseline   : %s", baseline)
    log.info("Target     : %s", target)
    log.info("Run ID     : %s", run_id)

    # Phase 1: fetch
    log.info("Phase 1/6: Fetching repository …")
    try:
        await clone_or_fetch(clone_url, repo_dir)
    except GitError as exc:
        log.error("Git fetch failed: %s", exc)
        return 1

    # Phase 2: merge-base
    log.info("Phase 2/6: Resolving merge-base …")
    merge_base = await resolve_merge_base(repo_dir, baseline, target)
    history_rewrite = await detect_history_rewrite(repo_dir, baseline, target)
    if history_rewrite:
        log.warning("History rewrite detected — diff may be over-inclusive")
    log.info("Merge-base: %s", merge_base)

    # Phase 3: diff extraction
    log.info("Phase 3/6: Extracting diff …")
    try:
        numstat = await get_diff_numstat(repo_dir, merge_base, target)
        name_status = await get_diff_name_status(repo_dir, merge_base, target)
    except GitError as exc:
        log.error("Diff extraction failed: %s", exc)
        return 1

    units = parse_diff(numstat, name_status, run_id, repo_name, baseline, target)
    log.info("Files changed: %d", len(units))

    # Phase 4: hunk extraction
    log.info("Phase 4/6: Extracting hunks …")
    hunks_map: dict[str, str] = {}
    if units:
        try:
            hunks_map = await extract_all_hunks(repo_dir, merge_base, target, units, hunks_dir)
        except Exception as exc:
            log.warning("Hunk extraction partially failed: %s", exc)
    log.info("Hunks extracted: %d", len(hunks_map))

    cu_objs = [_cu_from_dict(u, hunks_map) for u in units]

    # Phase 5: agent review (optional)
    log.info("Phase 5/6: Agent review …")
    raw_findings, _agent_metrics = await _run_agent_review(cu_objs, concurrency)
    findings = _to_finding_objs(raw_findings)

    # Phase 6: scoring + report
    log.info("Phase 6/6: Scoring and rendering report …")
    score_result = compute_score(findings)

    fake_score = _Score(
        final_score=score_result.final_score,
        grade=score_result.grade,
        confidence=score_result.confidence,
        deductions=score_result.deductions,
        caps=score_result.caps,
        limitations=score_result.limitations,
    )
    fake_run = _Run(
        run_id=run_id,
        target_branch="(shadow)",
        target_sha=target[:40],
        baseline_sha=baseline[:40],
        started_at=started_at,
        completed_at=datetime.now(UTC),
    )

    markdown = render_markdown(
        run=fake_run,
        repository_full_name=repo_name,
        score=fake_score,
        findings=findings,
        change_units=cu_objs,
    )

    # Output
    print(markdown)
    if output:
        output.write_text(markdown, encoding="utf-8")
        log.info("Report saved to: %s", output)

    log.info(
        "Done — Score: %.1f (%s) | Findings: %d | Files: %d",
        score_result.final_score,
        score_result.grade,
        len(findings),
        len(units),
    )
    return 0


def _resolve_default_clone_url(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        out = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        out = ""
    if not out:
        raise SystemExit("Missing --clone-url (and no git remote.origin.url found in cwd)")
    return out


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def _format_benchmark_markdown(
    *,
    clone_url: str,
    target_ref: str,
    samples: int,
    metrics: list[SampleMetrics],
) -> str:
    latencies = [m.agent_latency_s for m in metrics]
    tokens = [m.input_tokens + m.output_tokens for m in metrics]
    providers = sorted({m.provider for m in metrics})
    if latencies:
        latency_p50 = f"| agent latency p50 | {statistics.median(latencies):.2f}s |"
        latency_p95 = f"| agent latency p95 | {_percentile(latencies, 95):.2f}s |"
    else:
        latency_p50 = "| agent latency p50 | n/a |"
        latency_p95 = "| agent latency p95 | n/a |"

    if tokens:
        tokens_p50 = f"| tokens p50 (in+out) | {statistics.median(tokens):.0f} |"
        tokens_p95 = f"| tokens p95 (in+out) | {_percentile(tokens, 95):.0f} |"
    else:
        tokens_p50 = "| tokens p50 | n/a |"
        tokens_p95 = "| tokens p95 | n/a |"

    lines = [
        "",
        f"## Shadow pilot benchmark ({datetime.now(UTC).date().isoformat()})",
        "",
        f"- clone_url: `{clone_url}`",
        f"- target ref: `{target_ref}`",
        f"- samples requested: {samples}",
        f"- samples completed: {len(metrics)}",
        f"- provider(s): {', '.join(providers)}",
        "",
        "| metric | value |",
        "|---|---|",
        latency_p50,
        latency_p95,
        tokens_p50,
        tokens_p95,
        f"| findings total | {sum(m.findings for m in metrics)} |",
        "",
        "### Per-sample detail",
        "",
        "| # | baseline | target | files | reviewable | latency(s) | tokens | findings |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for i, m in enumerate(metrics, 1):
        tok = m.input_tokens + m.output_tokens
        lines.append(
            f"| {i} | `{m.baseline_sha[:8]}` | `{m.target_sha[:8]}` | "
            f"{m.files_changed} | {m.reviewable_files} | {m.agent_latency_s:.2f} | "
            f"{tok} | {m.findings} |"
        )
    lines.append("")
    return "\n".join(lines)


async def _list_commit_pairs(
    repo_dir: Path,
    target_ref: str,
    count: int,
) -> list[tuple[str, str]]:
    from devmanager_git.fetcher import GitError, resolve_sha, run_git

    target_sha = await resolve_sha(repo_dir, target_ref)
    log_out = await run_git(
        ["git", "log", "-n", str(count), "--format=%H", target_sha],
        repo_dir,
    )
    commits = [line.strip() for line in log_out.splitlines() if line.strip()]
    pairs: list[tuple[str, str]] = []
    for commit in commits:
        try:
            parent = (await run_git(["git", "rev-parse", f"{commit}^"], repo_dir)).strip()
        except GitError:
            continue
        pairs.append((parent, commit))
    return pairs


async def run_benchmark_samples(
    clone_url: str,
    target: str,
    samples: int,
    workspace: Path,
    concurrency: int,
    output: Path | None,
    repository_name: str | None,
) -> int:
    _import_packages()

    from devmanager_git.differ import parse_diff
    from devmanager_git.fetcher import (
        GitError,
        clone_or_fetch,
        get_diff_name_status,
        get_diff_numstat,
    )
    from devmanager_git.hunks import extract_all_hunks

    repo_name = repository_name or clone_url.rstrip("/").rstrip(".git").rsplit("/", 2)[-1]
    if "/" not in repo_name:
        repo_name = f"shadow/{repo_name}"

    workspace.mkdir(parents=True, exist_ok=True)
    repo_dir = workspace / "repo.git"

    log.info("=== Shadow Pilot Benchmark (%d samples) ===", samples)
    log.info("Repository : %s", repo_name)
    log.info("Clone URL  : %s", clone_url)
    log.info("Target ref : %s", target)

    try:
        await clone_or_fetch(clone_url, repo_dir)
    except GitError as exc:
        log.error("Git fetch failed: %s", exc)
        return 1

    pairs = await _list_commit_pairs(repo_dir, target, samples)
    if not pairs:
        log.error("No commit pairs found for target %r", target)
        return 1

    log.info("Collected %d commit pair(s) from git log", len(pairs))
    collected: list[SampleMetrics] = []

    for i, (baseline_sha, target_sha) in enumerate(pairs, 1):
        run_id = uuid.uuid4()
        hunks_dir = workspace / "hunks" / f"bench-{i}-{run_id.hex[:8]}"
        log.info(
            "Sample %d/%d: %s..%s",
            i,
            len(pairs),
            baseline_sha[:8],
            target_sha[:8],
        )
        try:
            numstat = await get_diff_numstat(repo_dir, baseline_sha, target_sha)
            name_status = await get_diff_name_status(repo_dir, baseline_sha, target_sha)
        except GitError as exc:
            log.warning("Sample %d diff failed: %s", i, exc)
            continue

        units = parse_diff(
            numstat,
            name_status,
            run_id,
            repo_name,
            baseline_sha,
            target_sha,
        )
        hunks_map: dict[str, str] = {}
        if units:
            try:
                hunks_map = await extract_all_hunks(
                    repo_dir,
                    baseline_sha,
                    target_sha,
                    units,
                    hunks_dir,
                )
            except Exception as exc:
                log.warning("Sample %d hunk extraction failed: %s", i, exc)

        cu_objs = [_cu_from_dict(u, hunks_map) for u in units]
        reviewable = [
            u for u in cu_objs if not u.is_binary and not u.is_generated and not u.is_vendor
        ]
        raw_findings, agent_metrics = await _run_agent_review(
            cu_objs,
            concurrency,
            force_mock=not (os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")),
        )
        collected.append(
            SampleMetrics(
                baseline_sha=baseline_sha,
                target_sha=target_sha,
                files_changed=len(units),
                reviewable_files=len(reviewable),
                agent_latency_s=float(agent_metrics.get("latency_s", 0.0)),
                findings=len(raw_findings),
                input_tokens=int(agent_metrics.get("input_tokens", 0)),
                output_tokens=int(agent_metrics.get("output_tokens", 0)),
                llm_calls=int(agent_metrics.get("llm_calls", 0)),
                provider=str(agent_metrics.get("provider", "skipped")),
            )
        )

    report = _format_benchmark_markdown(
        clone_url=clone_url,
        target_ref=target,
        samples=samples,
        metrics=collected,
    )
    print(report)
    if output:
        existing = output.read_text(encoding="utf-8") if output.exists() else ""
        output.write_text(existing.rstrip() + report, encoding="utf-8")
        log.info("Benchmark appended to: %s", output)

    if collected:
        latencies = [m.agent_latency_s for m in collected]
        log.info(
            "Benchmark done — %d samples | latency p50=%.2fs p95=%.2fs",
            len(collected),
            statistics.median(latencies),
            _percentile(latencies, 95),
        )
    return 0 if collected else 1


def main():
    parser = argparse.ArgumentParser(
        description="DevManager Shadow Pilot — read-only code review trial run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--clone-url", default=None, help="Git clone URL (https or ssh)")
    parser.add_argument("--baseline", default=None, help="Baseline commit SHA or branch")
    parser.add_argument("--target", default=None, help="Target commit SHA or branch")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Save report/benchmark to file (benchmark mode appends)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("/tmp/devmanager/shadow"),
        help="Local workspace for bare clone and hunks (default: /tmp/devmanager/shadow)",
    )
    parser.add_argument(
        "--repo-name",
        default=None,
        help='Override repository name shown in report (e.g. "org/repo")',
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Max concurrent reviewer calls (default: 3)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=0,
        metavar="N",
        help="Benchmark mode: run N consecutive commits from --target (default ref: HEAD)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.samples > 0:
        clone_url = _resolve_default_clone_url(args.clone_url)
        target = args.target or "HEAD"
        exit_code = asyncio.run(
            run_benchmark_samples(
                clone_url=clone_url,
                target=target,
                samples=args.samples,
                workspace=args.workspace,
                output=args.output,
                concurrency=args.concurrency,
                repository_name=args.repo_name,
            )
        )
        sys.exit(exit_code)

    if not args.clone_url or not args.baseline or not args.target:
        parser.error(
            "single-run mode requires --clone-url, --baseline, and --target "
            "(or use --samples N for benchmark mode)"
        )

    exit_code = asyncio.run(
        run_shadow_pilot(
            clone_url=args.clone_url,
            baseline=args.baseline,
            target=args.target,
            workspace=args.workspace,
            output=args.output,
            concurrency=args.concurrency,
            repository_name=args.repo_name,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
