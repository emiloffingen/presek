import asyncio

from core import http_pool


def _reset():
    http_pool._async_clients.clear()


def test_async_client_reused_within_loop():
    _reset()

    async def run():
        return http_pool.get_async_client("crawler", 15.0) is http_pool.get_async_client("crawler", 15.0)

    assert asyncio.run(run()) is True


def test_dead_loop_clients_are_evicted():
    _reset()

    async def run():
        http_pool.get_async_client("robots", 10.0)
        http_pool.get_async_client("crawler", 15.0)

    for _ in range(50):
        asyncio.run(run())

    # Only the most recent loop's clients may remain; earlier closed loops are dropped.
    assert len(http_pool._async_clients) <= 2


def test_distinct_loops_get_distinct_clients():
    _reset()

    async def run():
        return http_pool.get_async_client("jina", 30.0)

    first = asyncio.run(run())
    second = asyncio.run(run())
    assert first is not second
