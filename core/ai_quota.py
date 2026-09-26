"""Per-provider daily request budgets for the free-tier LLM cascade.

The providers we use enforce their own quotas with HTTP 429s, but hitting the
wall mid-cascade wastes a round-trip and (for OpenRouter) can burn the whole
day's allowance on a single burst. This module keeps a lightweight per-day
counter in Redis so the cascade can skip a provider *before* it is exhausted.

Design notes:
  * Fail-open. If Redis is unavailable we allow the call; the provider's own
    429 handling remains the backstop.
  * Limits are per-provider calendar day (UTC) and overridable per provider via
    ``AI_DAILY_LIMIT_<PROVIDER>``. A limit of ``0`` disables the provider in the
    cascade (useful for dead accounts).
  * The guard stops at ``AI_QUOTA_SKIP_RATIO`` (default 0.9) of the limit so a
    few requests are always held back for retries.
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
    "openrouter": 50,
    "mistral": 0,
    "mistral2": 0,
}

_KEY_NAMESPACE = "ai:quota"
_KEY_TTL_SECONDS = 60 * 60 * 48  # keep 2 days so yesterday's counter expires naturally


def _enabled() -> bool:
    return os.environ.get("AI_QUOTA_GUARD_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _skip_ratio() -> float:
    try:
        ratio = float(os.environ.get("AI_QUOTA_SKIP_RATIO", "0.9"))
    except (TypeError, ValueError):
        ratio = 0.9
    return min(1.0, max(0.1, ratio))


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


def _counter_key(provider: str) -> str:
    day = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    return f"{_KEY_NAMESPACE}:{provider}:{day}"


def _client():
    from utils.cache import redis_client

    return redis_client


def usage(provider: str) -> int:
    """Requests already sent to ``provider`` today (UTC). Fail-open to 0."""
    try:
        raw = _client().get(_counter_key(provider))
        return int(raw) if raw is not None else 0
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("[ai/quota] usage read failed for %s: %s", provider, exc)
        return 0


def record_usage(provider: str, amount: int = 1) -> int:
    """Increment today's request counter for ``provider``. Fail-open."""
    if daily_limit(provider) is None:
        return 0
    try:
        client = _client()
        key = _counter_key(provider)
        total = client.incrby(key, max(1, int(amount)))
        client.expire(key, _KEY_TTL_SECONDS)
        return int(total)
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


def snapshot() -> dict[str, dict[str, int | None]]:
    """Observability helper: limit + usage for every provider with a limit."""
    out: dict[str, dict[str, int | None]] = {}
    for provider, default in DEFAULT_DAILY_LIMITS.items():
        limit = daily_limit(provider)
        out[provider] = {"limit": limit, "used": usage(provider) if limit else 0}
    return out
