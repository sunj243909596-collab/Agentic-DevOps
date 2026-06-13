from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api_gateway.error import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from api_gateway.routers import (
    analysis_runs,
    audit_events,
    change_units,
    findings,
    publication_requests,
    report,
    repositories,
    review,
    score,
    settings,
    trigger_events,
    webhook,
    webhook_gitlab,
)
from api_gateway.routers.code_map.router import router as code_map_router

load_dotenv()

log = logging.getLogger(__name__)
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")


@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── ARQ pool (optional — only when REDIS_URL is set) ─────────────────────
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            application.state.arq_pool = await create_pool(RedisSettings.from_dsn(redis_url))
            log.info("ARQ pool connected: %s", redis_url)
        except Exception as exc:
            log.warning("ARQ pool unavailable (%s) — async jobs disabled", exc)
            application.state.arq_pool = None
    else:
        application.state.arq_pool = None

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    pool = getattr(application.state, "arq_pool", None)
    if pool is not None:
        await pool.close()
        log.info("ARQ pool closed")


app = FastAPI(
    title="DevManager API Gateway",
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(trigger_events.router)
app.include_router(analysis_runs.router)
app.include_router(repositories.router)
app.include_router(change_units.router)
app.include_router(review.router)
app.include_router(score.router)
app.include_router(report.router)
app.include_router(findings.router)
app.include_router(audit_events.router)
app.include_router(publication_requests.router)
app.include_router(webhook.router)
app.include_router(webhook_gitlab.router)
app.include_router(settings.router)
app.include_router(code_map_router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}
