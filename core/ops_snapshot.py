"""Single-screen editorial ops snapshot for the admin cockpit."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from core.database import db_manager as db
from core.health import (
    _REDIS_KEY,
    _freshness_payload,
    _get_redis,
    _probe_celery_queue,
    get_synthesis_quality_snapshot,
)
from core.limits import CELERY_QUEUE_CRITICAL_DEPTH, CELERY_QUEUE_WARN_DEPTH
from core.queue_status import queue_status_payload, reader_pipeline_status

_STALE_CLUSTER_SQL = """
WITH recent AS (
    SELECT cluster_id, MAX(COALESCE(ingested_at, created_at)) AS latest_article_at
    FROM articles
    WHERE created_at >= NOW() - INTERVAL '24 hours'
    GROUP BY cluster_id
),
summaries AS (
    SELECT cluster_id, MAX(created_at) AS synthesis_at
    FROM cluster_summaries
    GROUP BY cluster_id
),
stale AS (
    SELECT r.cluster_id, r.latest_article_at
    FROM recent r
    LEFT JOIN summaries s USING (cluster_id)
    WHERE s.synthesis_at IS NULL
       OR r.latest_article_at > s.synthesis_at + INTERVAL '45 minutes'
)
SELECT
    (SELECT COUNT(*) FROM stale) AS stale_count,
    COALESCE(
        (
            SELECT json_agg(cluster_id ORDER BY latest_article_at DESC)
            FROM (
                SELECT cluster_id, latest_article_at
                FROM stale
                ORDER BY latest_article_at DESC
                LIMIT 8
            ) sample
        ),
        '[]'::json
    ) AS sample_ids
"""


def _load_last_refresh_time() -> str | None:
    try:
        raw = _get_redis().get(_REDIS_KEY)
        if not raw:
            return None
        payload = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return payload.get("time")
    except Exception:
        return None


def _alert(severity: str, code: str, message: str, metric: str | None = None) -> dict:
    item = {"severity": severity, "code": code, "message": message}
    if metric is not None:
        item["metric"] = metric
    return item


def _derive_status(alerts: list[dict]) -> str:
    if any(item.get("severity") == "critical" for item in alerts):
        return "critical"
    if any(item.get("severity") == "warn" for item in alerts):
        return "warn"
    return "ok"


async def build_ops_snapshot() -> dict:
    celery = _probe_celery_queue()
    queues = queue_status_payload()
    pipeline = reader_pipeline_status()
    synthesis = get_synthesis_quality_snapshot() or {}
    primary = synthesis.get("primary") or {}
    history = synthesis.get("history") or {}

    freshness = _freshness_payload(_load_last_refresh_time())
    unsummarized_total = int(synthesis.get("unsummarized_total") or 0)
    unsummarized_24h = int(synthesis.get("unsummarized_24h") or 0)
    fallback_ratio_24h = float(primary.get("fallback_ratio") or 0.0)
    fallback_ratio_7d = float(history.get("fallback_ratio") or 0.0)
    synthesis_status = str(synthesis.get("status") or "unknown")

    stale_row = await db.async_execute_one(_STALE_CLUSTER_SQL) or {}
    stale_count = int(stale_row.get("stale_count") or 0)
    sample_ids = stale_row.get("sample_ids") or []
    if isinstance(sample_ids, str):
        sample_ids = json.loads(sample_ids)

    total_depth = int(celery.get("total_depth") or 0)
    max_depth = int(celery.get("celery_depth") or 0)
    alerts: list[dict] = []

    if total_depth >= CELERY_QUEUE_CRITICAL_DEPTH:
        alerts.append(
            _alert(
                "critical",
                "queue_critical",
                f"Celery backlog critical ({total_depth} pending tasks).",
                str(total_depth),
            )
        )
    elif celery.get("degraded") or total_depth >= CELERY_QUEUE_WARN_DEPTH:
        alerts.append(
            _alert(
                "warn",
                "queue_elevated",
                f"Celery backlog elevated ({total_depth} pending tasks).",
                str(total_depth),
            )
        )

    if freshness.get("status") == "stale":
        alerts.append(
            _alert(
                "warn",
                "ingestion_lag",
                f"Ingestion refresh lagging ({freshness.get('label', 'stale')}).",
                str(freshness.get("age_minutes") or ""),
            )
        )

    if synthesis_status == "critical":
        alerts.append(
            _alert(
                "critical",
                "synthesis_quality",
                "24h synthesis fallback ratio is critical.",
                f"{fallback_ratio_24h:.1%}",
            )
        )
    elif synthesis_status == "warn":
        alerts.append(
            _alert(
                "warn",
                "synthesis_quality",
                "24h synthesis fallback ratio is elevated.",
                f"{fallback_ratio_24h:.1%}",
            )
        )

    if unsummarized_24h >= 1500:
        alerts.append(
            _alert(
                "warn",
                "synthesis_backlog",
                f"High unsummarized volume in last 24h ({unsummarized_24h}).",
                str(unsummarized_24h),
            )
        )

    if stale_count >= 8:
        alerts.append(
            _alert(
                "warn",
                "stale_clusters",
                f"{stale_count} active clusters need synthesis refresh.",
                str(stale_count),
            )
        )

    busiest_queue = max(
        (queues.get("depths") or {}).items(),
        key=lambda item: int(item[1] or 0),
        default=("none", 0),
    )

    return {
        "status": _derive_status(alerts),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
        "ingestion": {
            "freshness_status": freshness.get("status"),
            "age_minutes": freshness.get("age_minutes"),
            "label": freshness.get("label"),
        },
        "synthesis": {
            "quality_status": synthesis_status,
            "fallback_ratio_24h": round(fallback_ratio_24h, 4),
            "fallback_ratio_7d": round(fallback_ratio_7d, 4),
            "unsummarized_total": unsummarized_total,
            "unsummarized_24h": unsummarized_24h,
            "providers_24h": primary.get("providers") or {},
            "providers_7d": history.get("providers") or {},
        },
        "queues": {
            "intel_status": queues.get("intel_status"),
            "intel_heavy_depth": queues.get("intel_heavy_depth"),
            "total_depth": total_depth,
            "max_depth": max_depth,
            "busiest_queue": busiest_queue[0],
            "busiest_queue_depth": int(busiest_queue[1] or 0),
            "depths": queues.get("depths") or {},
        },
        "pipeline": pipeline,
        "stale_clusters": {
            "count": stale_count,
            "sample_cluster_ids": list(sample_ids)[:8],
        },
    }
