"""Per-provider daily request budgets for the free-tier LLM cascade.

The providers enforce their own quotas with HTTP 429s, but hitting the wall
mid-cascade wastes a round-trip and (for OpenRouter) can burn the day's whole
allowance on one burst. This module keeps a shared per-day counter so the
cascade can skip a provider *before* it is exhausted.

Storage is the shared Postgres database (both production hosts already use it),
NOT Redis — Redis is the Celery broker/result backend, so sharing it would merge
the two hosts' task queues. Postgres gives us one aggregate counter across every
host for free.

Design notes:
  * Fail-open. Any storage error disables the guard for that call; the
    provider's own 429 handling remains the backstop.
  * Limits are per-provider UTC calendar day, overridable per provider via
    ``AI_DAILY_LIMIT_<PROVIDER>``. A limit of ``0`` disables the provider.
  * The guard stops at ``AI_QUOTA_SKIP_RATIO`` (default 0.9) of the limit so a
    few requests are always held back for retries.
  * Usage reads are cached in-process for ``AI_QUOTA_READ_TTL_SECONDS`` to avoid
    a DB round-trip before every provider attempt.
"""

from __future__ import annotations

import datetime
import logging
import os

log = logging.getLogger("presek")

# Free-tier daily request ceilings (approximate, verified against provider
# headers / account endpoints in Sep 2026). Override with AI_DAILY_LIMIT_<NAME>.
DEFAULT_DAILY_LIMITS: dict[str, int] = {
    "groq": 1000,
    "gemini": 1000,
    "gemini2": 1000,
    "gemini3": 1000,
    "nvidia": 1000,
    "openrouter": 50,
}

_TABLE = "ai_provider_usage"
_TABLE_READY = False
_READ_CACHE: dict[str, tuple[float, int]] = {}

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    provider      TEXT        NOT NULL,
    usage_day     DATE        NOT NULL,
    request_count INTEGER     NOT NULL DEFAULT 0,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, usage_day)
)
"""

_UPSERT_SQL = f"""
INSERT INTO {_TABLE} (provider, usage_day, request_count, updated_at)
VALUES (%s, (NOW() AT TIME ZONE 'UTC')::date, %s, NOW())
ON CONFLICT (provider, usage_day)
DO UPDATE SET request_count = {_TABLE}.request_count + EXCLUDED.request_count,
              updated_at = NOW()
RETURNING request_count
"""  # nosec B608 - _TABLE is a module constant; values are bound params

_SELECT_SQL = f"""
SELECT request_count FROM {_TABLE}
WHERE provider = %s AND usage_day = (NOW() AT TIME ZONE 'UTC')::date
"""  # nosec B608 - _TABLE is a module constant; values are bound params


def _enabled() -> bool:
    return os.environ.get("AI_QUOTA_GUARD_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _skip_ratio() -> float:
    try:
        ratio = float(os.environ.get("AI_QUOTA_SKIP_RATIO", "0.9"))
    except (TypeError, ValueError):
        ratio = 0.9
    return min(1.0, max(0.1, ratio))


def _read_ttl() -> float:
    try:
        return max(0.0, float(os.environ.get("AI_QUOTA_READ_TTL_SECONDS", "20")))
    except (TypeError, ValueError):
        return 20.0


def daily_limit(provider: str) -> int | None:
    """Return the configured daily request ceiling, or None when unlimited/unknown."""
    env_key = f"AI_DAILY_LIMIT_{provider.upper()}"
    raw = os.environ.get(env_key)
    if raw is not None and raw.strip() != "":
        try:
            return max(0, int(float(raw)))
        except (TypeError, ValueError):
            log.warning("[ai/quota] invalid %s=%r; ignoring", env_key, raw)
    return DEFAULT_DAILY_LIMITS.get(provider)


# --- storage primitives (monkeypatch points for tests) ---------------------


def _ensure_table_sync() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        from core.database import db_manager

        db_manager.execute(_DDL, fetch=False, read_only=False)
    except Exception as exc:  # table likely already exists (other host created it)
        log.debug("[ai/quota] ensure table (sync): %s", exc)
    _TABLE_READY = True


async def _ensure_table_async() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        from core.database import db_manager

        await db_manager.async_execute(_DDL, fetch=False, read_only=False)
    except Exception as exc:
        log.debug("[ai/quota] ensure table (async): %s", exc)
    _TABLE_READY = True


def _db_add_usage(provider: str, amount: int) -> int:
    _ensure_table_sync()
    from core.database import db_manager

    rows = db_manager.execute(_UPSERT_SQL, (provider, amount), read_only=False)
    if rows and rows[0]:
        return int(rows[0]["request_count"])
    return 0


def _db_get_usage(provider: str) -> int:
    from core.database import db_manager

    rows = db_manager.execute(_SELECT_SQL, (provider,), read_only=False)
    if rows and rows[0]:
        return int(rows[0]["request_count"])
    return 0


async def _db_add_usage_async(provider: str, amount: int) -> int:
    await _ensure_table_async()
    from core.database import db_manager

    rows = await db_manager.async_execute(_UPSERT_SQL, (provider, amount), read_only=False)
    if rows and rows[0]:
        return int(rows[0]["request_count"])
    return 0


async def _db_get_usage_async(provider: str) -> int:
    from core.database import db_manager

    rows = await db_manager.async_execute(_SELECT_SQL, (provider,), read_only=False)
    if rows and rows[0]:
        return int(rows[0]["request_count"])
    return 0


def _cache_get(provider: str) -> int | None:
    entry = _READ_CACHE.get(provider)
    if not entry:
        return None
    ts, value = entry
    if (datetime.datetime.now(datetime.UTC).timestamp() - ts) > _read_ttl():
        return None
    return value


def _cache_put(provider: str, value: int) -> None:
    _READ_CACHE[provider] = (datetime.datetime.now(datetime.UTC).timestamp(), value)


def reset_cache() -> None:
    """Clear the in-process usage cache (used by tests)."""
    _READ_CACHE.clear()


# --- public API -------------------------------------------------------------


def usage(provider: str) -> int:
    """Requests already sent to ``provider`` today (UTC), shared across hosts."""
    cached = _cache_get(provider)
    if cached is not None:
        return cached
    try:
        value = _db_get_usage(provider)
        _cache_put(provider, value)
        return value
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[ai/quota] usage read failed for %s: %s", provider, exc)
        return 0


def record_usage(provider: str, amount: int = 1) -> int:
    """Increment today's shared request counter for ``provider``. Fail-open."""
    if daily_limit(provider) is None:
        return 0
    try:
        total = _db_add_usage(provider, max(1, int(amount)))
        _cache_put(provider, total)
        return total
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[ai/quota] usage write failed for %s: %s", provider, exc)
        return 0


def is_exhausted(provider: str) -> bool:
    """True when the provider should be skipped for the rest of the UTC day."""
    if not _enabled():
        return False
    limit = daily_limit(provider)
    if limit is None:
        return False
    if limit <= 0:
        return True
    threshold = max(1, int(limit * _skip_ratio()))
    return usage(provider) >= threshold


async def async_usage(provider: str) -> int:
    cached = _cache_get(provider)
    if cached is not None:
        return cached
    try:
        value = await _db_get_usage_async(provider)
        _cache_put(provider, value)
        return value
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[ai/quota] async usage read failed for %s: %s", provider, exc)
        return 0


async def async_record_usage(provider: str, amount: int = 1) -> int:
    if daily_limit(provider) is None:
        return 0
    try:
        total = await _db_add_usage_async(provider, max(1, int(amount)))
        _cache_put(provider, total)
        return total
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[ai/quota] async usage write failed for %s: %s", provider, exc)
        return 0


async def async_is_exhausted(provider: str) -> bool:
    if not _enabled():
        return False
    limit = daily_limit(provider)
    if limit is None:
        return False
    if limit <= 0:
        return True
    threshold = max(1, int(limit * _skip_ratio()))
    return await async_usage(provider) >= threshold


def _providers_with_limits() -> list[str]:
    return list(DEFAULT_DAILY_LIMITS.keys())


def snapshot() -> dict[str, dict[str, int | None]]:
    """Observability helper: limit + usage for every provider with a limit."""
    out: dict[str, dict[str, int | None]] = {}
    for provider in _providers_with_limits():
        limit = daily_limit(provider)
        out[provider] = {"limit": limit, "used": usage(provider) if limit else 0}
    return out


async def async_snapshot() -> dict[str, dict[str, int | None]]:
    out: dict[str, dict[str, int | None]] = {}
    for provider in _providers_with_limits():
        limit = daily_limit(provider)
        out[provider] = {"limit": limit, "used": await async_usage(provider) if limit else 0}
    return out
