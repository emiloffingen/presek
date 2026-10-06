import asyncio

import pytest

from core.database import async_db, db_manager
from routes.stats import _register_pending_subscriber


def _subscribers_table_ready() -> bool:
    try:
        db_manager.execute("SELECT email, is_active FROM subscribers LIMIT 1")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _subscribers_table_ready(), reason="needs the migrated Postgres test database")

_EMAIL = "race-test@example.mk"


async def _scenario():
    try:
        db_manager.execute("DELETE FROM subscribers WHERE email = %s", (_EMAIL,), fetch=False)

        results = await asyncio.gather(
            *[_register_pending_subscriber(_EMAIL, "mk") for _ in range(5)], return_exceptions=True
        )

        # A double-click must not raise (unique constraint on subscribers.email)...
        assert not [r for r in results if isinstance(r, Exception)], results
        assert results == [False] * 5

        # ...must leave exactly one row...
        row = db_manager.execute_one(
            "SELECT count(*) AS n, bool_or(is_active) AS active FROM subscribers WHERE email = %s", (_EMAIL,)
        )
        assert row["n"] == 1
        # ...and the address stays inactive until the emailed link is used.
        assert row["active"] is False
    finally:
        db_manager.execute("DELETE FROM subscribers WHERE email = %s", (_EMAIL,), fetch=False)
        if async_db._pool is not None:
            await async_db._pool.close()
            async_db._pool = None
        if getattr(async_db, "_read_pool", None) is not None:
            await async_db._read_pool.close()
            async_db._read_pool = None


def test_simultaneous_newsletter_signups_create_one_inactive_row():
    async_db._pool = None
    asyncio.run(_scenario())
