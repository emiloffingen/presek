"""
http_pool.py - Shared HTTP connection pool for performance optimization.

Provides a centralized connection pool for httpx clients to enable:
- Connection reuse across requests
- Reduced TCP handshake overhead
- Better resource utilization
- Configurable pool sizes per use case
"""

import atexit
import logging
import os
from typing import Optional

import httpx

log = logging.getLogger("presek")

# Configuration from environment
DEFAULT_TIMEOUT = float(os.environ.get("HTTP_POOL_TIMEOUT", "30.0"))
MAX_CONNECTIONS = int(os.environ.get("HTTP_POOL_MAX_CONNECTIONS", "100"))
MAX_KEEPALIVE_CONNECTIONS = int(os.environ.get("HTTP_POOL_MAX_KEEPALIVE", "20"))

# Shared clients for different use cases
_SHARED_CLIENT: Optional[httpx.Client] = None
_SHARED_ASYNC_CLIENT: Optional[httpx.AsyncClient] = None
_SHARED_FEED_CLIENT: Optional[httpx.Client] = None
_SHARED_AI_CLIENT: Optional[httpx.Client] = None


def get_shared_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.Client:
    """Get or create a shared synchronous HTTP client with connection pooling."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=MAX_CONNECTIONS,
                max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
            ),
            follow_redirects=True,
        )
        atexit.register(_cleanup_shared_client)
        log.info(f"[http_pool] Created shared sync client with {MAX_CONNECTIONS} max connections")
    return _SHARED_CLIENT


def get_shared_async_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """Get or create a shared async HTTP client with connection pooling."""
    global _SHARED_ASYNC_CLIENT
    if _SHARED_ASYNC_CLIENT is None:
        _SHARED_ASYNC_CLIENT = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=MAX_CONNECTIONS,
                max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
            ),
            follow_redirects=True,
        )
        atexit.register(_cleanup_shared_async_client)
        log.info(f"[http_pool] Created shared async client with {MAX_CONNECTIONS} max connections")
    return _SHARED_ASYNC_CLIENT


def get_feed_client(timeout: float = 10.0) -> httpx.Client:
    """Get or create a shared HTTP client optimized for feed fetching.
    
    Feed fetching benefits from:
    - Higher connection limits (many feeds to fetch)
    - Shorter timeouts (feeds should be fast)
    - Redirect following (feeds often move)
    """
    global _SHARED_FEED_CLIENT
    if _SHARED_FEED_CLIENT is None:
        _SHARED_FEED_CLIENT = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=max(50, MAX_CONNECTIONS),
                max_keepalive_connections=max(20, MAX_KEEPALIVE_CONNECTIONS),
            ),
            follow_redirects=True,
        )
        atexit.register(_cleanup_feed_client)
        log.info(f"[http_pool] Created feed client with {max(50, MAX_CONNECTIONS)} max connections")
    return _SHARED_FEED_CLIENT


def get_ai_client(timeout: float = 120.0) -> httpx.Client:
    """Get or create a shared HTTP client optimized for AI API calls.
    
    AI API calls benefit from:
    - Longer timeouts (LLM inference can be slow)
    - Lower connection limits (fewer concurrent AI calls)
    - No redirect following (APIs typically don't redirect)
    """
    global _SHARED_AI_CLIENT
    if _SHARED_AI_CLIENT is None:
        _SHARED_AI_CLIENT = httpx.Client(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=10,  # Fewer concurrent AI calls
                max_keepalive_connections=5,
            ),
            follow_redirects=False,
        )
        atexit.register(_cleanup_ai_client)
        log.info("[http_pool] Created AI client with 10 max connections")
    return _SHARED_AI_CLIENT


def _cleanup_shared_client():
    """Clean up the shared synchronous client."""
    global _SHARED_CLIENT
    if _SHARED_CLIENT is not None:
        try:
            _SHARED_CLIENT.close()
            log.info("[http_pool] Closed shared sync client")
        except Exception as e:
            log.warning(f"[http_pool] Error closing shared sync client: {e}")
        _SHARED_CLIENT = None


def _cleanup_shared_async_client():
    """Clean up the shared async client."""
    global _SHARED_ASYNC_CLIENT
    if _SHARED_ASYNC_CLIENT is not None:
        try:
            import asyncio
            asyncio.run(_SHARED_ASYNC_CLIENT.aclose())
            log.info("[http_pool] Closed shared async client")
        except Exception as e:
            log.warning(f"[http_pool] Error closing shared async client: {e}")
        _SHARED_ASYNC_CLIENT = None


def _cleanup_feed_client():
    """Clean up the feed client."""
    global _SHARED_FEED_CLIENT
    if _SHARED_FEED_CLIENT is not None:
        try:
            _SHARED_FEED_CLIENT.close()
            log.info("[http_pool] Closed feed client")
        except Exception as e:
            log.warning(f"[http_pool] Error closing feed client: {e}")
        _SHARED_FEED_CLIENT = None


def _cleanup_ai_client():
    """Clean up the AI client."""
    global _SHARED_AI_CLIENT
    if _SHARED_AI_CLIENT is not None:
        try:
            _SHARED_AI_CLIENT.close()
            log.info("[http_pool] Closed AI client")
        except Exception as e:
            log.warning(f"[http_pool] Error closing AI client: {e}")
        _SHARED_AI_CLIENT = None


def cleanup_all():
    """Clean up all shared HTTP clients."""
    _cleanup_shared_client()
    _cleanup_shared_async_client()
    _cleanup_feed_client()
    _cleanup_ai_client()


def get_pool_stats() -> dict:
    """Get statistics about the connection pools."""
    stats = {}
    
    if _SHARED_CLIENT is not None:
        pool = _SHARED_CLIENT._connection_pool
        stats["sync_client"] = {
            "connections": len(pool._connection_cache),
            "max_connections": MAX_CONNECTIONS,
        }
    
    if _SHARED_FEED_CLIENT is not None:
        pool = _SHARED_FEED_CLIENT._connection_pool
        stats["feed_client"] = {
            "connections": len(pool._connection_cache),
            "max_connections": max(50, MAX_CONNECTIONS),
        }
    
    if _SHARED_AI_CLIENT is not None:
        pool = _SHARED_AI_CLIENT._connection_pool
        stats["ai_client"] = {
            "connections": len(pool._connection_cache),
            "max_connections": 10,
        }
    
    return stats
