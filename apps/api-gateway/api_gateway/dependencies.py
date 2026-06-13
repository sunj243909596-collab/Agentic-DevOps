from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:sinopharm%401089@localhost:5432/agent_devops",
)
_API_SECRET_KEY = os.getenv("API_SECRET_KEY", "change-me-in-production")

_engine = create_async_engine(_DATABASE_URL, pool_size=5, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


async def require_auth(authorization: str | None = Header(default=None)) -> str:
    if _API_SECRET_KEY == "change-me-in-production":
        return "anonymous"
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = authorization.removeprefix("Bearer ").strip()
    if token != _API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token
