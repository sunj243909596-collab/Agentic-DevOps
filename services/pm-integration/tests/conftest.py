"""pm-integration 集成测试 fixtures：复用 db 包相同的 PG 连接。"""

from __future__ import annotations

import os

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:sinopharm%401089@localhost:5432/agent_devops",
)


@pytest_asyncio.fixture
async def db_engine():
    eng = create_async_engine(_DATABASE_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(db_engine) -> AsyncSession:
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
