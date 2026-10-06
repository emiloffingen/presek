import asyncio
import time

import pytest

from core.database import async_db, db_manager


def _postgres_available() -> bool:
    try:
        db_manager.execute("SELECT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="needs a Postgres test database")


async def _scenario():
    try:
        started = time.monotonic()
        with pytest.raises(Exception) as exc:
            await db_manager.async_execute("SELECT pg_sleep(5)", read_only=True, timeout_ms=200)
        elapsed = time.monotonic() - started

        # Postgres itself cancelled the statement, long before the 5 s sleep finished.
        assert elapsed < 3
        assert "timeout" in str(exc.value).lower() or "cancel" in str(exc.value).lower()

        # The pooled connection is healthy and the 200 ms limit did not leak into the next query.
        rows = await db_manager.async_execute(
            "SELECT 1 AS ok, current_setting('statement_timeout') AS st", read_only=True
        )
        assert rows[0]["ok"] == 1
        assert rows[0]["st"] != "200ms"

        # Without a timeout, queries behave exactly as before.
        rows = await db_manager.async_execute("SELECT pg_sleep(0.05), 2 AS two", read_only=True)
        assert rows[0]["two"] == 2

        # A generous timeout does not cancel a fast query.
        rows = await db_manager.async_execute("SELECT 3 AS three", read_only=True, timeout_ms=5000)
        assert rows[0]["three"] == 3
    finally:
        if async_db._pool is not None:
            await async_db._pool.close()
            async_db._pool = None
        if getattr(async_db, "_read_pool", None) is not None:
            await async_db._read_pool.close()
            async_db._read_pool = None


def test_async_statement_timeout_cancels_slow_query_and_keeps_pool_healthy():
    async_db._pool = None
    asyncio.run(_scenario())
