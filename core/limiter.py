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
        ip = None
        try:
            from routes.common import _client_ip_for_request

            ip = _client_ip_for_request(request)
        except Exception:
            log.debug("Rate limiter check failed")

        if not ip:
            try:
                ip = get_remote_address(request)
            except Exception:
                ip = "0.0.0.0"

        if ip in ("127.0.0.1", "::1", "localhost", "0.0.0.0"):
            return "local"
        return ip

    RateLimitExceeded = errors.RateLimitExceeded
    _rate_limiter_enabled = True
    _slowapi_redis_url = "memory://"
    limiter = Limiter(
        key_func=get_custom_client_ip,
        default_limits=["1000/minute", "12000/hour"],
        storage_uri=_slowapi_redis_url,
    )
except ImportError as exc:
    if os.environ.get("ENV") == "production" and "pytest" not in sys.modules:
        raise RuntimeError("slowapi is required when ENV=production") from exc
    log.warning("Rate limiting disabled - slowapi not installed")
    RateLimitExceeded = _RateLimitExceededFallback


def custom_rate_limit(limit_str):
    """Factory for rate limit decorators (no-op if slowapi not installed)."""
    if "pytest" in sys.modules:
        return lambda f: f
    if _rate_limiter_enabled and limiter:
        return limiter.limit(limit_str)
    return lambda f: f


def exempt_from_rate_limit(func):
    """Decorator that exempts from rate limiting (no-op if slowapi not installed)."""
    if _rate_limiter_enabled and limiter:
        return limiter.exempt(func)
    return func
