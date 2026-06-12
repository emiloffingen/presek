"""Operational Celery queue depth helpers for admin UI and metrics."""

from core.health import MONITORED_CELERY_QUEUES
from core.limits import (
    CELERY_QUEUE_WARN_DEPTH,
    INTEL_QUEUE_FULL_DEFER_LIMIT,
    INTEL_QUEUE_SECONDARY_DEFER_LIMIT,
    INTEL_QUEUE_SOFT_DEFER_LIMIT,
)
from tasks.utils import get_celery_queue_depth


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


def queue_status_payload() -> dict:
    depths = get_all_queue_depths()
    intel_depth = depths.get("intel-heavy", 0)
    return {
        "depths": depths,
        "intel_heavy_depth": intel_depth,
        "intel_status": get_intel_backlog_status(intel_depth),
        "thresholds": {
            "soft": INTEL_QUEUE_SOFT_DEFER_LIMIT,
            "secondary": INTEL_QUEUE_SECONDARY_DEFER_LIMIT,
            "full": INTEL_QUEUE_FULL_DEFER_LIMIT,
            "warn": CELERY_QUEUE_WARN_DEPTH,
        },
    }


def reader_pipeline_status() -> dict:
    """Public-safe pipeline snapshot for reader-facing stale badges and /status."""
    payload = queue_status_payload()
    intel_depth = int(payload.get("intel_heavy_depth") or 0)
    return {
        "busy": intel_depth >= CELERY_QUEUE_WARN_DEPTH,
        "intel_status": payload.get("intel_status") or "ok",
        "intel_heavy_depth": intel_depth,
        "warn_threshold": CELERY_QUEUE_WARN_DEPTH,
        "thresholds": payload.get("thresholds") or {},
    }
