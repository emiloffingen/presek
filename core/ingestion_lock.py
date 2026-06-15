"""Redis mutex for serializing long-running ingestion cycles."""

from __future__ import annotations

import logging

from utils import redis_client

log = logging.getLogger(__name__)

INGESTION_LOCK_KEY = "lock:run_ingestion"
INGESTION_LOCK_TTL_SECONDS = 3600


def try_acquire_ingestion_lock() -> bool | None:
    """Return True when acquired, False when busy, None when Redis is unavailable."""
    try:
        return bool(redis_client.set(INGESTION_LOCK_KEY, "1", nx=True, ex=INGESTION_LOCK_TTL_SECONDS))
    except Exception as exc:
        log.error("[ingestion] Redis lock acquire failed: %s", exc)
        return None


def renew_ingestion_lock() -> bool:
    try:
        return bool(redis_client.expire(INGESTION_LOCK_KEY, INGESTION_LOCK_TTL_SECONDS))
    except Exception as exc:
        log.debug("[ingestion] Redis lock renew failed: %s", exc)
        return False


def release_ingestion_lock() -> None:
    try:
        redis_client.delete(INGESTION_LOCK_KEY)
    except Exception as exc:
        log.debug("[ingestion] Redis lock release failed: %s", exc)


def is_ingestion_in_flight() -> bool:
    try:
        return bool(redis_client.exists(INGESTION_LOCK_KEY))
    except Exception as exc:
        log.debug("[ingestion] Redis lock probe failed: %s", exc)
        return False
