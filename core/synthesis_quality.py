"""Tiered synthesis quality thresholds and runtime event helpers."""

from __future__ import annotations

import os

from core.limits import (
    SYNTHESIS_QUALITY_MIN_LOCAL,
    SYNTHESIS_QUALITY_MIN_MISTRAL_LARGE,
    SYNTHESIS_QUALITY_MIN_MISTRAL_SMALL,
    SYNTHESIS_QUALITY_MIN_NVIDIA,
)


def synthesis_quality_threshold(provider: str | None, *, fast_mode: bool = False) -> float | None:
    """Minimum quality score for a provider; None skips the gate (fast mode)."""
    if fast_mode:
        return None

    normalized = (provider or "").strip().lower()
    thresholds = {
        "local": SYNTHESIS_QUALITY_MIN_LOCAL,
        "mistral_small": SYNTHESIS_QUALITY_MIN_MISTRAL_SMALL,
        "mistral_large": SYNTHESIS_QUALITY_MIN_MISTRAL_LARGE,
        "nvidia": SYNTHESIS_QUALITY_MIN_NVIDIA,
    }
    return thresholds.get(normalized, SYNTHESIS_QUALITY_MIN_MISTRAL_SMALL)


def synthesis_needs_upgrade(
    fallback_reason: str | None = None,
    generation_provider: str | None = None,
) -> bool:
    """True when a published synthesis should be re-run at full quality."""
    reason = (fallback_reason or "").strip().lower()
    provider = (generation_provider or "").strip().lower()
    if reason == "fast_mode_provisional":
        return True
    if provider == "enhanced_fallback":
        return True
    return "enhanced_fallback" in reason


def build_synthesis_meta(
    row: dict | None,
    *,
    lang: str = "sr",
) -> dict:
    """Public metadata block for cluster synthesis generation."""
    row = row or {}
    fallback_reason = row.get("fallback_reason")
    generation_provider = row.get("generation_provider")
    return {
        "lang": lang,
        "generation_provider": generation_provider,
        "generation_model": row.get("generation_model"),
        "quality_score": row.get("quality_score"),
        "fallback_reason": fallback_reason,
        "is_provisional": fallback_reason == "fast_mode_provisional",
        "needs_upgrade": synthesis_needs_upgrade(fallback_reason, generation_provider),
    }


def count_low_score_syntheses(*, min_score: float = 0.75, days: int = 7) -> int:
    """Count recent non-fallback summaries below the quality floor."""
    from core.database import db_manager as db

    row = db.execute(
        """
        SELECT COUNT(*) AS low_score_count
        FROM cluster_summaries
        WHERE quality_score IS NOT NULL
          AND quality_score < %s
          AND created_at >= NOW() - (%s || ' days')::interval
          AND COALESCE(generation_provider, '') NOT IN ('enhanced_fallback', '')
        """,
        (float(min_score), max(1, int(days))),
        read_only=True,
    )
    data = row[0] if row else {}
    return int(data.get("low_score_count") or 0)


def count_upgradeable_syntheses(*, days: int = 7) -> dict[str, int]:
    """Count provisional and enhanced_fallback summaries in the recent window."""
    from core.database import db_manager as db

    row = db.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE fallback_reason = 'fast_mode_provisional') AS provisional_count,
            COUNT(*) FILTER (
                WHERE generation_provider = 'enhanced_fallback'
                   OR COALESCE(fallback_reason, '') ILIKE '%%enhanced_fallback%%'
            ) AS fallback_count
        FROM cluster_summaries
        WHERE created_at >= NOW() - (%s || ' days')::interval
        """,
        (max(1, int(days)),),
        read_only=True,
    )
    data = row[0] if row else {}
    return {
        "provisional_count": int(data.get("provisional_count") or 0),
        "fallback_count": int(data.get("fallback_count") or 0),
    }


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


def mark_fast_synthesis_pending(cluster_id: str) -> None:
    """Track clusters published in fast mode awaiting full upgrade."""
    from utils import redis_client

    if not cluster_id or not os.environ.get("REDIS_URL"):
        return
    ttl = int(os.environ.get("FAST_SYNTHESIS_PENDING_TTL_SECONDS", str(48 * 3600)))
    try:
        redis_client.setex(f"presek:fast_synthesis_pending:{cluster_id}", ttl, "1")
    except Exception:
        pass


def clear_fast_synthesis_pending(cluster_id: str) -> None:
    from utils import redis_client

    if not cluster_id or not os.environ.get("REDIS_URL"):
        return
    try:
        redis_client.delete(f"presek:fast_synthesis_pending:{cluster_id}")
    except Exception:
        pass


def count_stuck_fast_syntheses(max_age_hours: int) -> int:
    return len(list_stuck_fast_synthesis_cluster_ids(max_age_hours=max_age_hours))


def list_stuck_fast_synthesis_cluster_ids(
    *,
    max_age_hours: int,
    limit: int = 100,
) -> list[str]:
    """Return cluster IDs whose fast-mode upgrade is still pending past max_age_hours."""
    from utils import redis_client

    if not os.environ.get("REDIS_URL"):
        return []

    ttl_seconds = int(os.environ.get("FAST_SYNTHESIS_PENDING_TTL_SECONDS", str(48 * 3600)))
    min_age_seconds = max(0, int(max_age_hours)) * 3600
    stuck: list[str] = []
    prefix = "presek:fast_synthesis_pending:"

    try:
        for key in redis_client.scan_iter(f"{prefix}*", count=200):
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            if not key_str.startswith(prefix):
                continue
            ttl = redis_client.ttl(key_str)
            if ttl is None or ttl < 0:
                stuck.append(key_str.removeprefix(prefix))
            else:
                age_seconds = max(0, ttl_seconds - int(ttl))
                if age_seconds >= min_age_seconds:
                    stuck.append(key_str.removeprefix(prefix))
            if len(stuck) >= max(1, int(limit)):
                break
    except Exception:
        return stuck

    return stuck[: max(1, int(limit))]
