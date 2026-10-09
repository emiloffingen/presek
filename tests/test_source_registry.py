"""get_source_registry must never block the asyncio event loop on the database."""

import asyncio
import threading
import time
from unittest.mock import patch

from utils import db_helpers


def _reset():
    db_helpers._SOURCE_REGISTRY_CACHE.update({"time": 0.0, "data": {}})
    db_helpers._SOURCE_REGISTRY_REFRESHING.clear()


class _FakeDb:
    def __init__(self, rows, delay=0.0):
        self.rows = rows
        self.delay = delay
        self.threads = []

    def execute(self, sql, *a, **kw):
        self.threads.append(threading.current_thread())
        time.sleep(self.delay)
        return self.rows


def _with_db(fake):
    return patch("core.database.db_manager", fake)


def test_off_loop_keeps_blocking_database_overlay():
    _reset()
    fake = _FakeDb([{"name": "TestSource", "credibility": 1.9, "category": "Cat"}])
    with _with_db(fake):
        reg = db_helpers.get_source_registry()
    assert reg["TestSource"]["credibility"] == 1.9
    assert fake.threads and fake.threads[0] is threading.current_thread()


def test_on_loop_returns_immediately_and_refreshes_in_background():
    _reset()
    fake = _FakeDb([{"name": "TestSource", "credibility": 1.9, "category": "Cat"}], delay=0.5)

    async def scenario():
        loop_thread = threading.current_thread()
        t0 = time.monotonic()
        reg = db_helpers.get_source_registry()
        elapsed = time.monotonic() - t0
        # Cold start: hardcoded registry, no waiting for the slow database.
        assert elapsed < 0.2
        assert "TestSource" not in reg
        # The refresh runs in another thread and lands in the cache afterwards.
        for _ in range(40):
            await asyncio.sleep(0.05)
            if db_helpers._SOURCE_REGISTRY_CACHE["data"].get("TestSource"):
                break
        assert db_helpers._SOURCE_REGISTRY_CACHE["data"]["TestSource"]["credibility"] == 1.9
        assert fake.threads and all(t is not loop_thread for t in fake.threads)
        return db_helpers.get_source_registry()

    with _with_db(fake):
        reg = asyncio.run(scenario())
    assert reg["TestSource"]["credibility"] == 1.9


def test_on_loop_serves_stale_cache_while_refreshing():
    _reset()
    db_helpers._SOURCE_REGISTRY_CACHE.update({"time": time.time() - 10_000, "data": {"Old": {"name": "Old"}}})
    fake = _FakeDb([], delay=0.3)

    async def scenario():
        t0 = time.monotonic()
        reg = db_helpers.get_source_registry()
        assert time.monotonic() - t0 < 0.2
        return reg

    with _with_db(fake):
        reg = asyncio.run(scenario())
        time.sleep(0.6)
    assert reg == {"Old": {"name": "Old"}}
