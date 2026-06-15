"""Redis mutex for serializing long-running ingestion cycles."""

from __future__ import annotations

import contextvars
import logging
import uuid

from utils import redis_client

log = logging.getLogger(__name__)

INGESTION_LOCK_KEY = "lock:run_ingestion"
INGESTION_LOCK_TTL_SECONDS = 3600

_lock_owner: contextvars.ContextVar[str | None] = contextvars.ContextVar("ingestion_lock_owner", default=None)

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""

_RENEW_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
else
  return 0
end
"""


def try_acquire_ingestion_lock() -> bool | None:
    """Return True when acquired, False when busy, None when Redis is unavailable."""
    owner = uuid.uuid4().hex
    try:
        acquired = redis_client.set(INGESTION_LOCK_KEY, owner, nx=True, ex=INGESTION_LOCK_TTL_SECONDS)
        if acquired:
            _lock_owner.set(owner)
            return True
        return False
    except Exception as exc:
        log.error("[ingestion] Redis lock acquire failed: %s", exc)
        return None


def renew_ingestion_lock() -> bool:
    owner = _lock_owner.get()
    if not owner:
        log.warning("[ingestion] Lock renew skipped: no local owner token")
        return False
    try:
        renewed = bool(
            redis_client.eval(
                _RENEW_SCRIPT,
                1,
                INGESTION_LOCK_KEY,
                owner,
                INGESTION_LOCK_TTL_SECONDS,
            )
        )
        if not renewed:
            log.warning("[ingestion] Lock renew failed: lock lost or owned by another worker")
        return renewed
    except Exception as exc:
        log.warning("[ingestion] Redis lock renew failed: %s", exc)
        return False


def release_ingestion_lock() -> None:
    owner = _lock_owner.get()
    if not owner:
        return
    try:
        released = bool(redis_client.eval(_RELEASE_SCRIPT, 1, INGESTION_LOCK_KEY, owner))
        if not released:
            log.warning("[ingestion] Lock release skipped: not owner or lock already expired")
    except Exception as exc:
        log.debug("[ingestion] Redis lock release failed: %s", exc)
    finally:
        _lock_owner.set(None)


def is_ingestion_in_flight() -> bool:
    try:
        return bool(redis_client.exists(INGESTION_LOCK_KEY))
    except Exception as exc:
        log.debug("[ingestion] Redis lock probe failed: %s", exc)
        return False
