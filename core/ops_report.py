"""Weekly editorial ops quality report."""

from __future__ import annotations

from datetime import datetime, timezone

from core.database import db_manager as db
from core.ops_snapshot import build_ops_snapshot


async def build_weekly_ops_report() -> dict:
    ops = await build_ops_snapshot()

    synthesis_rows = await db.async_execute(
        """
        SELECT COALESCE(NULLIF(generation_provider, ''), 'unknown') AS provider,
               COUNT(*) AS count
        FROM cluster_summaries
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY 1
        ORDER BY count DESC
        """,
        read_only=True,
    ) or []

    tag_noise = await db.async_execute(
        """
        SELECT tag, COUNT(*) AS count
        FROM (
            SELECT unnest(tags) AS tag
            FROM cluster_metadata
            WHERE updated_at >= NOW() - INTERVAL '7 days'
        ) t
        WHERE length(tag) <= 2 OR tag ~ '[0-9]{4,}'
        GROUP BY 1
        ORDER BY count DESC
        LIMIT 8
        """,
        read_only=True,
    ) or []

    source_gaps = await db.async_execute(
        """
        SELECT source, COUNT(*) AS articles_7d
        FROM articles
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY source
        HAVING COUNT(*) = 1
        ORDER BY articles_7d DESC
        LIMIT 10
        """,
        read_only=True,
    ) or []

    total_providers = sum(int(row.get("count") or 0) for row in synthesis_rows)
    fallback = sum(
        int(row.get("count") or 0)
        for row in synthesis_rows
        if str(row.get("provider") or "").lower() in ("enhanced_fallback", "local", "unknown")
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": 7,
        "ops": ops,
        "synthesis": {
            "providers_7d": {row["provider"]: int(row["count"]) for row in synthesis_rows},
            "total_7d": total_providers,
            "fallback_ratio_7d": round(fallback / total_providers, 4) if total_providers else 0.0,
        },
        "tag_noise_samples": [
            {"tag": row["tag"], "count": int(row["count"])} for row in tag_noise
        ],
        "single_hit_sources_7d": [
            {"source": row["source"], "articles": int(row["articles_7d"])} for row in source_gaps
        ],
    }
