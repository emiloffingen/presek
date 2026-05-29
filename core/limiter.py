import logging
import os
import sys

log = logging.getLogger("presek.limiter")

_rate_limiter_enabled = False
limiter = None


class _RateLimitExceededFallback(Exception):
    """Fallback if slowapi is not installed."""

    def __init__(self, detail=None, retry_after=None):
        self.detail = detail
        self.retry_after = retry_after


try:
    from slowapi import Limiter, errors
    from slowapi.util import get_remote_address

    def get_custom_client_ip(request) -> str:
        try:
            if hasattr(request, "client") and request.client:
                host = request.client.host
                if host in ("127.0.0.1", "::1"):
                    return None
        except Exception:
            pass
        return get_remote_address(request)

    RateLimitExceeded = errors.RateLimitExceeded
    _rate_limiter_enabled = True
    limiter = Limiter(
        key_func=get_custom_client_ip,
        default_limits=["1000/minute", "12000/hour"],
        storage_uri=(
            "memory://"
            if "pytest" in sys.modules
            else os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        ),
    )
except ImportError as exc:
    if os.environ.get("ENV") == "production" and "pytest" not in sys.modules:
        raise RuntimeError("slowapi is required when ENV=production") from exc
    log.warning("Rate limiting disabled - slowapi not installed")
    RateLimitExceeded = _RateLimitExceededFallback


def custom_rate_limit(limit_str):
    """Factory for rate limit decorators (no-op if slowapi not installed)."""
    if _rate_limiter_enabled and limiter:
        return limiter.limit(limit_str)
    return lambda f: f


def exempt_from_rate_limit(func):
    """Decorator that exempts from rate limiting (no-op if slowapi not installed)."""
    if _rate_limiter_enabled and limiter:
        return limiter.exempt(func)
    return func
