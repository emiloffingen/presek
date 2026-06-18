"""Redis mutex for serializing long-running ingestion cycles."""

from __future__ import annotations

import contextvars
import logging
import time
import uuid

from utils import redis_client

log = logging.getLogger(__name__)

INGESTION_LOCK_KEY = "lock:run_ingestion"
INGESTION_LOCK_TTL_SECONDS = 3600
INGESTION_TASK_NAME = "tasks.ingestion_task.run_ingestion"
STALE_INGESTION_LOCK_SECONDS = 1800

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


def _lock_value(owner: str) -> str:
    return f"{owner}:{int(time.time())}"


def _ingestion_celery_task_active() -> bool | None:
    """Return True/False when inspect succeeds, None when inspect is unavailable."""
    try:
        from core.celery_app import celery_app

        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        for tasks in active.values():
            for task in tasks or []:
                if task.get("name") == INGESTION_TASK_NAME:
                    return True
        return False
    except Exception as exc:
        log.debug("[ingestion] Celery inspect failed while checking active ingestion: %s", exc)
        return None


def break_stale_ingestion_lock(max_age_seconds: int = STALE_INGESTION_LOCK_SECONDS) -> bool:
    """Clear a Redis ingestion lock left behind by a dead worker."""
    try:
        raw = redis_client.get(INGESTION_LOCK_KEY)
        if not raw:
            return False
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
    except Exception as exc:
        log.warning("[ingestion] Failed to read ingestion lock: %s", exc)
        return False

    active = _ingestion_celery_task_active()
    if active is True:
        return False
    if active is None:
        parts = raw.split(":", 1)
        if len(parts) == 2:
            try:
                started = int(parts[1])
            except ValueError:
                started = 0
            if started and time.time() - started <= max_age_seconds:
                return False
        else:
            return False

    try:
        redis_client.delete(INGESTION_LOCK_KEY)
        log.warning("[ingestion] Cleared stale ingestion lock")
        return True
    except Exception as exc:
        log.warning("[ingestion] Failed to clear stale ingestion lock: %s", exc)
        return False


def try_acquire_ingestion_lock() -> bool | None:
    """Return True when acquired, False when busy, None when Redis is unavailable."""
    owner = uuid.uuid4().hex
    value = _lock_value(owner)
    try:
        acquired = redis_client.set(INGESTION_LOCK_KEY, value, nx=True, ex=INGESTION_LOCK_TTL_SECONDS)
        if acquired:
            _lock_owner.set(value)
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
