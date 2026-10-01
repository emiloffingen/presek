"""Shared HTTP connection pool.

Centralizes outbound httpx clients so TCP/TLS handshakes are reused across
requests (crawler, feed fetching, Jina embeddings, images, ...).

Two entry points:

- ``get_shared_client(timeout)``: one long-lived synchronous ``httpx.Client``
  per timeout. Safe to share across threads.
- ``get_async_client(name, timeout, follow_redirects)``: one ``httpx.AsyncClient``
  per (event loop, name, timeout, follow_redirects). Keying by the running loop
  matters because this deployment runs code under uvicorn's loop, Celery's loop,
  and ad-hoc ``asyncio.run`` loops; a client created on a dead loop must never be
  reused. Stale-loop clients are detected and replaced.

Callers pass per-request headers as usual (``client.get(url, headers=...)``).
"""

from __future__ import annotations

import asyncio
import atexit
import os
import threading
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

import httpx

DEFAULT_TIMEOUT = float(os.environ.get("HTTP_POOL_TIMEOUT", "30.0"))
MAX_CONNECTIONS = int(os.environ.get("HTTP_POOL_MAX_CONNECTIONS", "100"))
MAX_KEEPALIVE_CONNECTIONS = int(os.environ.get("HTTP_POOL_MAX_KEEPALIVE", "20"))

_sync_lock = threading.Lock()
_sync_clients: dict[float, httpx.Client] = {}

_async_lock = threading.Lock()
_async_clients: dict[tuple, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}


def _limits() -> httpx.Limits:
    return httpx.Limits(
        max_connections=MAX_CONNECTIONS,
        max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
    )


def get_shared_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.Client:
    """A process-wide synchronous client with connection pooling."""
    key = float(timeout)
    with _sync_lock:
        client = _sync_clients.get(key)
        if client is None or client.is_closed:
            client = httpx.Client(
                timeout=timeout,
                limits=_limits(),
                follow_redirects=True,
            )
            _sync_clients[key] = client
        return client


def get_async_client(
    name: str = "default",
    timeout: float = DEFAULT_TIMEOUT,
    follow_redirects: bool = True,
) -> httpx.AsyncClient:
    """An async client pooled per running event loop.

    ``name`` separates clients that want different settings even at the same
    timeout (e.g. crawler vs embeddings).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    key = (name, float(timeout), bool(follow_redirects), id(loop) if loop else 0)
    with _async_lock:
        entry = _async_clients.get(key)
        if entry is not None:
            entry_loop, client = entry
            if (
                entry_loop is not None
                and not entry_loop.is_closed()
                and not client.is_closed
            ):
                return client
        client = httpx.AsyncClient(
            timeout=timeout,
            limits=_limits(),
            follow_redirects=follow_redirects,
        )
        if loop is not None:
            _async_clients[key] = (loop, client)
        return client


@contextmanager
def pooled_client(timeout: float = DEFAULT_TIMEOUT) -> Iterator[httpx.Client]:
    """Yield the shared sync client without closing it on exit."""
    yield get_shared_client(timeout)


@asynccontextmanager
async def pooled_async_client(
    name: str = "default",
    timeout: float = DEFAULT_TIMEOUT,
    follow_redirects: bool = True,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a loop-pooled async client without closing it on exit."""
    yield get_async_client(name, timeout, follow_redirects)


@atexit.register
def _cleanup() -> None:
    for client in list(_sync_clients.values()):
        try:
            client.close()
        except Exception:
            pass
    for _loop, client in list(_async_clients.values()):
        try:
            if not client.is_closed:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(client.aclose())
                finally:
                    loop.close()
        except Exception:
            pass
