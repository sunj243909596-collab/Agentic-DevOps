"""
ARQ background tasks for the DevManager analysis pipeline.

Each task receives an ARQ context dict containing:
  ctx["make_session"]  — async_sessionmaker (created by on_startup)
  ctx["engine"]        — AsyncEngine (disposed by on_shutdown)
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path

from devmanager_db.daos.analysis_run import AnalysisRunDAO
from devmanager_db.daos.setting import SettingDAO
from devmanager_db.secrets import decrypt_secret
from devmanager_git.service import ingest
from devmanager_reporting.service import generate_report
from devmanager_scoring.service import score_run

log = logging.getLogger(__name__)

REVIEW_TIMEOUT_SEC = int(os.getenv("REVIEW_TIMEOUT_SEC", "1800"))


def _resolve_repo_dir(repository_id: uuid.UUID) -> Path:
    workspace = Path(os.getenv("REPO_WORKSPACE", "/tmp/devmanager/repos"))
    d = workspace / str(repository_id)
    if not (d / "HEAD").exists():
        raise FileNotFoundError(f"repo not cloned at {d}")
    return d


async def _load_llm_provider(db):
    """Build an LLMProvider from the settings table (DB-driven config).

    Reads:
      - llm_provider   provider key (e.g. "claude", "mock")
      - llm_api_key    Fernet-encrypted; decrypted in-memory only
      - llm_model      model name; falls back to provider default
      - llm_base_url   optional custom endpoint (Claude only; empty = SDK default)

    Returns None if the configured provider requires credentials that are
    missing (e.g. claude with no key) — caller should skip agent review.
    """
    from devmanager_llm import make_provider, LLMAuthError

    dao = SettingDAO(db)
    name    = (await dao.get("llm_provider"))  or None
    api_key = (await dao.get("llm_api_key"))   or None
    model   = (await dao.get("llm_model"))     or None
    base_url = (await dao.get("llm_base_url")) or None

    if not name:
        log.info("llm_provider not configured — skipping agent review")
        return None
    name = name.value
    api_key_plain = decrypt_secret(api_key.value) if api_key and api_key.value else ""
    model_v = model.value if model else None
    base_url_v = (base_url.value or "").strip() if base_url else None

    try:
        provider = make_provider(
            name,
            api_key=api_key_plain,
            model=model_v,
            base_url=base_url_v or None,
        )
    except LLMAuthError as e:
        log.warning("LLM provider init failed: %s — skipping agent review", e)
        return None
    log.info(
        "LLM provider ready: name=%s model=%s base_url=%s",
        provider.name, model_v or "(default)", base_url_v or "(default)",
    )
    return provider


async def full_pipeline(
    ctx: dict,
    run_id_str: str,
    review_timeout_sec: int = REVIEW_TIMEOUT_SEC,
) -> dict:
    """Run the complete analysis pipeline for *run_id_str* in the background.

    Phases (each in a separate AsyncSession so failures stay isolated):
      1. Git ingestion      — clone/fetch, diff extraction, hunk extraction
      2. Agent review       — LLM-based agent loop review
                              (skipped when provider can't be initialised)
      3. Scoring            — deterministic score + grade
      4. Report generation  — Markdown report written to disk

    On any unhandled exception the run is marked ``failed`` and the
    exception is re-raised so ARQ can record it and apply retry logic.
    """
    run_id = uuid.UUID(run_id_str)
    make_session = ctx["make_session"]

    log.info("Pipeline started: run=%s", run_id)

    try:
        async with make_session() as db:
            await ingest(run_id, db)
        log.info("Ingestion complete: run=%s", run_id)

        async with make_session() as db:
            provider = await _load_llm_provider(db)
            if provider is not None:
                from devmanager_agents.service import review_run
                run = await AnalysisRunDAO(db).get_by_id(run_id)
                repo_dir = _resolve_repo_dir(run.repository_id)
                try:
                    await asyncio.wait_for(
                        review_run(run_id, db, provider, repo_dir=repo_dir),
                        timeout=review_timeout_sec,
                    )
                except TimeoutError:
                    log.error("review_run timed out after %ds: run=%s", review_timeout_sec, run_id)
                    await AnalysisRunDAO(db).update_status(
                        run_id,
                        "failed",
                        failure_reason=f"agent_review timed out after {review_timeout_sec}s",
                    )
                    await db.commit()
                    raise
            else:
                log.info("No LLM provider — skipping agent review: run=%s", run_id)
                await AnalysisRunDAO(db).update_status(run_id, "agent_review_completed")
                await db.commit()
        log.info("Review complete: run=%s", run_id)

        async with make_session() as db:
            await score_run(run_id, db)
        log.info("Scoring complete: run=%s", run_id)

        async with make_session() as db:
            await generate_report(run_id, db)
        log.info("Report complete: run=%s", run_id)

        async with make_session() as db:
            await AnalysisRunDAO(db).update_status(run_id, "completed")
            await db.commit()
        log.info("Pipeline completed: run=%s", run_id)
        return {"run_id": run_id_str, "status": "completed"}

    except Exception as exc:
        log.error("Pipeline failed: run=%s  error=%s", run_id, exc, exc_info=True)
        try:
            async with make_session() as db:
                await AnalysisRunDAO(db).update_status(
                    run_id, "failed", failure_reason=str(exc)[:500]
                )
                await db.commit()
        except Exception:
            pass
        raise
