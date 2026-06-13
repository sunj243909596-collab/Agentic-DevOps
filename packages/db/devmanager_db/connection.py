from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://devmanager:devmanager@localhost:5432/devmanager",
)
_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))

engine = create_async_engine(_DATABASE_URL, pool_size=_POOL_SIZE, echo=False)

_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
