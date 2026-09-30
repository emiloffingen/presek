"""Synthesis quality/state helpers.

The MK-only simplify pass stubbed this module, but the intelligence tasks were
later restored and still import several of these helpers. Keep the stubs, but
provide real (cheap) implementations for the symbols that are imported so the
modules load and runtime bookkeeping works.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("presek.synthesis_quality")

_FAST_PENDING_PREFIX = "presek:fast_synthesis_pending:"


def build_synthesis_meta(*a, **kw):
    return {}


def synthesis_needs_upgrade(*a, **kw):
    return False


def list_stuck_fast_synthesis_cluster_ids(*a, **kw):
    return []


def prune_stale_fast_synthesis_pending(*a, **kw):
    return 0


def count_low_score_syntheses(*a, **kw):
    return 0


def count_stuck_fast_syntheses(*a, **kw):
    return 0


def count_upgradeable_syntheses(*a, **kw):
    return {"provisional_count": 0, "fallback_count": 0}


def count_synthesis_persist_gap(*a, **kw):
    return {"synthesis_events": 0, "db_persisted_events": 0, "persist_gap": 0}


def synthesis_quality_threshold(provider: str | None, *, fast_mode: bool = False) -> float | None:
    """Minimum quality score for a provider; None skips the gate (fast mode)."""
    if fast_mode:
        return None
    from core.runtime_limits import SYNTHESIS_QUALITY_MIN_LOCAL, SYNTHESIS_QUALITY_MIN_NVIDIA

    thresholds = {
        "local": SYNTHESIS_QUALITY_MIN_LOCAL,
        "nvidia": SYNTHESIS_QUALITY_MIN_NVIDIA,
    }
    return thresholds.get((provider or "").strip().lower(), SYNTHESIS_QUALITY_MIN_NVIDIA)


def record_synthesis_runtime_event(
    *,
    provider: str,
    lang: str,
    fast_mode: bool,
    fallback_reason: str | None = None,
    cascade_depth: int | None = None,
) -> None:
    from utils import record_runtime_event

    fields = {
        "mode": provider or "unknown",
        "lang": lang,
        "fast_mode": fast_mode,
    }
    if fallback_reason:
        fields["reason"] = fallback_reason
    if cascade_depth is not None:
        fields["depth"] = cascade_depth
    record_runtime_event("synthesis_path", **fields)


def record_synthesis_db_persisted(
    *,
    cluster_id: str,
    lang: str,
    provider: str | None,
    fast_mode: bool,
) -> None:
    from utils import record_runtime_event

    record_runtime_event(
        "synthesis_db_persisted",
        cluster_id=cluster_id,
        lang=lang,
        mode=provider or "unknown",
        fast_mode=fast_mode,
    )


def mark_fast_synthesis_pending(cluster_id: str) -> None:
    """Track clusters published in fast mode awaiting full upgrade."""
    if not cluster_id or not os.environ.get("REDIS_URL"):
        return
    try:
        from utils import redis_client

        ttl = int(os.environ.get("FAST_SYNTHESIS_PENDING_TTL_SECONDS", str(48 * 3600)))
        redis_client.set(f"{_FAST_PENDING_PREFIX}{cluster_id}", "1", ex=ttl)
    except Exception:
        log.debug("mark_fast_synthesis_pending failed")


def clear_fast_synthesis_pending(cluster_id: str) -> None:
    if not cluster_id or not os.environ.get("REDIS_URL"):
        return
    try:
        from utils import redis_client

        redis_client.delete(f"{_FAST_PENDING_PREFIX}{cluster_id}")
    except Exception:
        log.debug("clear_fast_synthesis_pending failed")
