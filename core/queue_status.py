"""Operational Celery queue depth helpers for admin UI and metrics."""

from core.health import MONITORED_CELERY_QUEUES
from core.limits import (
    CELERY_QUEUE_WARN_DEPTH,
    FAST_TRACK_QUEUE_DEFER_LIMIT,
    FAST_TRACK_QUEUE_SOFT_LIMIT,
    INTEL_QUEUE_FULL_DEFER_LIMIT,
    INTEL_QUEUE_SECONDARY_DEFER_LIMIT,
    INTEL_QUEUE_SOFT_DEFER_LIMIT,
    MAINTENANCE_QUEUE_DEFER_LIMIT,
    PIPELINE_TOTAL_DEFER_DEPTH,
)
from utils import redis_client


def get_celery_queue_depth(queue_name: str = "celery") -> int:
    """Read Celery queue depth from Redis without importing worker task modules."""
    try:
        if queue_name != "celery":
            return int(redis_client.llen(queue_name) or 0)

        depths = [int(redis_client.llen(name) or 0) for name in MONITORED_CELERY_QUEUES]
        return max(depths) if depths else 0
    except Exception:
        return 0


def get_all_queue_depths() -> dict[str, int]:
    return {name: int(get_celery_queue_depth(name) or 0) for name in MONITORED_CELERY_QUEUES}


def get_intel_backlog_status(intel_depth: int | None = None) -> str:
    depth = int(get_celery_queue_depth("intel-heavy") if intel_depth is None else intel_depth)
    if depth >= INTEL_QUEUE_FULL_DEFER_LIMIT:
        return "backlogged"
    if depth >= INTEL_QUEUE_SECONDARY_DEFER_LIMIT:
        return "busy"
    if depth >= INTEL_QUEUE_SOFT_DEFER_LIMIT:
        return "elevated"
    return "ok"


def get_total_queue_depth() -> int:
    return int(sum(get_all_queue_depths().values()))


def get_fast_track_backlog_status(fast_track_depth: int | None = None) -> str:
    depth = int(get_celery_queue_depth("fast-track") if fast_track_depth is None else fast_track_depth)
    if depth >= FAST_TRACK_QUEUE_DEFER_LIMIT:
        return "backlogged"
    if depth >= FAST_TRACK_QUEUE_SOFT_LIMIT:
        return "busy"
    return "ok"


READER_PIPELINE_QUEUES = (
    "ingestion",
    "ingestion-crawl",
    "fast-track",
    "synthesis",
    "intel-heavy",
    "delivery",
)


def get_reader_relevant_queue_depth() -> int:
    depths = get_all_queue_depths()
    return int(sum(depths.get(name, 0) for name in READER_PIPELINE_QUEUES))


def get_pipeline_backlog_status(total_depth: int | None = None) -> str:
    depth = int(total_depth if total_depth is not None else get_reader_relevant_queue_depth())
    if depth >= PIPELINE_TOTAL_DEFER_DEPTH:
        return "critical"
    if depth >= CELERY_QUEUE_WARN_DEPTH * 4:
        return "backlogged"
    if depth >= CELERY_QUEUE_WARN_DEPTH:
        return "busy"
    return "ok"


def queue_status_payload() -> dict:
    depths = get_all_queue_depths()
    intel_depth = depths.get("intel-heavy", 0)
    fast_track_depth = depths.get("fast-track", 0)
    total_depth = int(sum(depths.values()))
    reader_depth = get_reader_relevant_queue_depth()
    return {
        "depths": depths,
        "total_depth": total_depth,
        "reader_queue_depth": reader_depth,
        "intel_heavy_depth": intel_depth,
        "fast_track_depth": fast_track_depth,
        "intel_status": get_intel_backlog_status(intel_depth),
        "fast_track_status": get_fast_track_backlog_status(fast_track_depth),
        "pipeline_status": get_pipeline_backlog_status(reader_depth),
        "thresholds": {
            "soft": INTEL_QUEUE_SOFT_DEFER_LIMIT,
            "secondary": INTEL_QUEUE_SECONDARY_DEFER_LIMIT,
            "full": INTEL_QUEUE_FULL_DEFER_LIMIT,
            "warn": CELERY_QUEUE_WARN_DEPTH,
            "fast_track_soft": FAST_TRACK_QUEUE_SOFT_LIMIT,
            "fast_track_defer": FAST_TRACK_QUEUE_DEFER_LIMIT,
            "maintenance_defer": MAINTENANCE_QUEUE_DEFER_LIMIT,
            "pipeline_total_defer": PIPELINE_TOTAL_DEFER_DEPTH,
        },
    }


def reader_pipeline_status() -> dict:
    """Public-safe pipeline snapshot for reader-facing stale badges and /status."""
    payload = queue_status_payload()
    intel_depth = int(payload.get("intel_heavy_depth") or 0)
    fast_track_depth = int(payload.get("fast_track_depth") or 0)
    reader_depth = int(payload.get("reader_queue_depth") or get_reader_relevant_queue_depth())
    pipeline_status = get_pipeline_backlog_status(reader_depth)
    return {
        "busy": pipeline_status in {"busy", "backlogged", "critical"}
        or intel_depth >= CELERY_QUEUE_WARN_DEPTH
        or fast_track_depth >= FAST_TRACK_QUEUE_SOFT_LIMIT,
        "intel_status": payload.get("intel_status") or "ok",
        "fast_track_status": payload.get("fast_track_status") or "ok",
        "pipeline_status": pipeline_status,
        "intel_heavy_depth": intel_depth,
        "fast_track_depth": fast_track_depth,
        "total_queue_depth": reader_depth,
        "warn_threshold": CELERY_QUEUE_WARN_DEPTH,
        "thresholds": payload.get("thresholds") or {},
    }
