import os
import logging

log = logging.getLogger("presek.limiter")

_rate_limiter_enabled = False
limiter = None

class RateLimitExceeded(Exception):
    """Fallback if slowapi is not installed."""
    def __init__(self, detail=None, retry_after=None):
        self.detail = detail
        self.retry_after = retry_after

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi import errors
    RateLimitExceeded = errors.RateLimitExceeded
    _rate_limiter_enabled = True
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100/minute", "1000/hour"],
        storage_uri=os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )
except ImportError:
    log.warning("Rate limiting disabled - slowapi not installed")

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
