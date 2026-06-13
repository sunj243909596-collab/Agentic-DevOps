#!/usr/bin/env python3
"""Run all pending SQL migrations against the configured PostgreSQL database."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

_CREATE_TRACKING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def applied_migrations(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT filename FROM schema_migrations")
    return {r["filename"] for r in rows}


async def apply_migration(conn: asyncpg.Connection, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute("INSERT INTO schema_migrations (filename) VALUES ($1)", sql_path.name)
    print(f"✓  {sql_path.name}")


async def main() -> None:
    raw_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://devmanager:devmanager@localhost:5432/devmanager",
    )
    dsn = raw_url.replace("postgresql+asyncpg://", "postgresql://")

    migrations_dir = Path(__file__).parent.parent / "migrations" / "postgres"
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print("No migration files found.")
        return

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:
        print(f"Cannot connect to database: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        await conn.execute(_CREATE_TRACKING)
        done = await applied_migrations(conn)
        pending = [f for f in sql_files if f.name not in done]
        if not pending:
            print("All migrations already applied.")
            return
        for sql_file in pending:
            await apply_migration(conn, sql_file)
        print(f"\nMigration complete — {len(pending)} file(s) applied.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
