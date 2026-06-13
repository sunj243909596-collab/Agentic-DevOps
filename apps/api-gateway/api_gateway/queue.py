"""ARQ pool dependency for FastAPI endpoints."""

from __future__ import annotations

from fastapi import Request


async def get_arq_pool(request: Request):
    """Return the ARQ Redis pool stored in app.state, or None if unavailable."""
    return getattr(request.app.state, "arq_pool", None)
