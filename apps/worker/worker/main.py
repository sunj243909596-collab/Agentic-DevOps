"""
ARQ Worker entry point.

Run with:
  arq worker.main.WorkerSettings

Environment variables:
  REDIS_URL      Redis connection DSN (default: redis://localhost:6379)
  DATABASE_URL   PostgreSQL DSN for async engine
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from worker.tasks import full_pipeline

load_dotenv()

log = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # Fallback for local dev only — in production always set DATABASE_URL via env
    "postgresql+asyncpg://postgres:sinopharm%401089@localhost:5432/agent_devops",
)
log.info("Worker DATABASE_URL host: %s", _DATABASE_URL.split("@")[-1] if "@" in _DATABASE_URL else "?")


async def startup(ctx: dict) -> None:
    """Create the shared DB engine and session factory; store in ARQ context."""
    engine = create_async_engine(_DATABASE_URL, pool_size=5, echo=False)
    ctx["engine"] = engine
    ctx["make_session"] = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    log.info("Worker DB pool initialised")


async def shutdown(ctx: dict) -> None:
    """Dispose the DB engine cleanly."""
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
        log.info("Worker DB pool disposed")


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [full_pipeline]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 5
    job_timeout = 3600  # 1 hour per job maximum
    keep_result = 3600  # keep job result in Redis for 1 hour


# Set redis_settings on the class once (ARQ reads it off the class object).
try:
    from arq.connections import RedisSettings as _RS

    WorkerSettings.redis_settings = _RS.from_dsn(_REDIS_URL)
except Exception:
    pass  # ARQ not installed in this environment
