"""Migrate session data (profiles + watchlist) from local JSON into Supabase.

Run when the main data load is incomplete but you need dashboard / watchlist working:
    python pipeline/migrate_session.py
"""
from __future__ import annotations

import asyncio
import os

from load import _migrate_session_data
from utils import get_logger

log = get_logger("pipeline.migrate_session")


async def main() -> None:
    import asyncpg

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required")
    conn = await asyncpg.connect(dsn)
    try:
        await _migrate_session_data(conn)
    finally:
        await conn.close()
    log.info("Session data migration complete")


if __name__ == "__main__":
    asyncio.run(main())
