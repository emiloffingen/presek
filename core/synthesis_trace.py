"""Per-cluster synthesis trace for admin debugging."""

from __future__ import annotations

import os

from core.database import db_manager as db
from core.synthesis_quality import (
    build_synthesis_meta,
    list_stuck_fast_synthesis_cluster_ids,
)
from utils import assess_cluster_synthesis_freshness


async def list_recent_synthesis_traces(lang: str = "sr", limit: int = 8) -> list[dict]:
    """Lightweight traces for clusters that likely need editorial attention."""
    lang = "mk" if str(lang or "").strip().lower().startswith("mk") else "sr"
    limit = max(1, min(int(limit or 8), 20))

    rows = await db.async_execute(
        """
        SELECT DISTINCT ON (s.cluster_id)
               s.cluster_id,
               s.lang,
               s.generation_provider,
               s.quality_score,
               s.fallback_reason,
               s.created_at,
               s.synthetic_headline
        FROM cluster_summaries s
        JOIN articles a ON a.cluster_id = s.cluster_id
        WHERE s.lang = %s
          AND (
                s.fallback_reason = 'fast_mode_provisional'
             OR s.generation_provider = 'enhanced_fallback'
             OR (s.quality_score IS NOT NULL AND s.quality_score < 0.75)
          )
          AND a.created_at >= NOW() - INTERVAL '48 hours'
        ORDER BY s.cluster_id, s.created_at DESC
        LIMIT %s
        """,
        (lang, limit * 3),
        read_only=True,
    )

    stuck_ids = set(list_stuck_fast_synthesis_cluster_ids(max_age_hours=24, limit=200))
    traces: list[dict] = []
    seen: set[str] = set()

    for row in rows or []:
        cid = str(row.get("cluster_id") or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        trace = await build_cluster_synthesis_trace(cid, lang=lang)
        trace["headline"] = row.get("synthetic_headline")
        trace["stuck_fast_upgrade"] = cid in stuck_ids
        traces.append(trace)
        if len(traces) >= limit:
            break

    if len(traces) < limit:
        from core.ops_snapshot import _STALE_CLUSTER_SQL

        stale_row = await db.async_execute_one(_STALE_CLUSTER_SQL) or {}
        sample_ids = stale_row.get("sample_ids") or []
        if isinstance(sample_ids, str):
            import json

            sample_ids = json.loads(sample_ids)
        for cid in sample_ids:
            cid = str(cid or "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            traces.append(await build_cluster_synthesis_trace(cid, lang=lang))
            if len(traces) >= limit:
                break

    return traces


async def build_cluster_synthesis_trace(cluster_id: str, lang: str = "sr") -> dict:
    """Assemble a single-screen synthesis debug trace for one cluster."""
    lang = "mk" if str(lang or "").strip().lower().startswith("mk") else "sr"

    articles = await db.async_execute(
        """
        SELECT id, title, source, created_at, ingested_at, category, topic, country
        FROM articles
        WHERE cluster_id = %s
        ORDER BY COALESCE(ingested_at, created_at) DESC, created_at DESC
        """,
        (cluster_id,),
        read_only=True,
    )
    summary_rows = await db.async_execute(
        """
        SELECT lang, summary, synthetic_headline, synthetic_standfirst, generated_article,
               generation_provider, generation_model, quality_score, fallback_reason,
               created_at, pulse_score, pluralism_score
        FROM cluster_summaries
        WHERE cluster_id = %s
        ORDER BY lang
        """,
        (cluster_id,),
        read_only=True,
    )
    history_rows = await db.async_execute(
        """
        SELECT lang, generation_provider, generation_model, quality_score,
               fallback_reason, created_at
        FROM cluster_summary_history
        WHERE cluster_id = %s
        ORDER BY created_at DESC
        LIMIT 12
        """,
        (cluster_id,),
        read_only=True,
    )

    summary_by_lang = {row.get("lang"): row for row in (summary_rows or [])}
    active = summary_by_lang.get(lang) or (summary_rows[0] if summary_rows else None)
    freshness = assess_cluster_synthesis_freshness(articles or [], (active or {}).get("created_at"))

    pending_upgrade = False
    if os.environ.get("REDIS_URL"):
        try:
            from utils import redis_client

            pending_upgrade = bool(redis_client.get(f"presek:fast_synthesis_pending:{cluster_id}"))
        except Exception:
            pending_upgrade = False

    stuck_ids = set(list_stuck_fast_synthesis_cluster_ids(max_age_hours=24, limit=500))

    languages = []
    for row in summary_rows or []:
        row_lang = row.get("lang") or "sr"
        meta = build_synthesis_meta(row, lang=row_lang)
        languages.append(
            {
                "lang": row_lang,
                "synthesis_meta": meta,
                "quality_score": row.get("quality_score"),
                "generation_provider": row.get("generation_provider"),
                "generation_model": row.get("generation_model"),
                "fallback_reason": row.get("fallback_reason"),
                "created_at": (row.get("created_at").isoformat() if row.get("created_at") else None),
                "pulse_score": row.get("pulse_score"),
                "pluralism_score": row.get("pluralism_score"),
                "has_headline": bool(str(row.get("synthetic_headline") or "").strip()),
                "has_article": bool(str(row.get("generated_article") or "").strip()),
            }
        )

    unique_sources = len({a.get("source") for a in (articles or []) if a.get("source")})
    return {
        "cluster_id": cluster_id,
        "lang": lang,
        "article_count": len(articles or []),
        "unique_sources": unique_sources,
        "countries": sorted({str(a.get("country") or "").upper() for a in (articles or []) if a.get("country")}),
        "freshness": freshness,
        "pending_fast_upgrade": pending_upgrade,
        "stuck_fast_upgrade": cluster_id in stuck_ids,
        "active_summary": build_synthesis_meta(active, lang=lang) if active else None,
        "languages": languages,
        "history": [
            {
                "lang": row.get("lang"),
                "generation_provider": row.get("generation_provider"),
                "generation_model": row.get("generation_model"),
                "quality_score": row.get("quality_score"),
                "fallback_reason": row.get("fallback_reason"),
                "created_at": (row.get("created_at").isoformat() if row.get("created_at") else None),
            }
            for row in (history_rows or [])
        ],
        "recommended_actions": _recommended_actions(
            active=active,
            freshness=freshness,
            pending_upgrade=pending_upgrade,
            stuck=cluster_id in stuck_ids,
            unique_sources=unique_sources,
        ),
    }


def _recommended_actions(
    *,
    active: dict | None,
    freshness: dict,
    pending_upgrade: bool,
    stuck: bool,
    unique_sources: int,
) -> list[str]:
    actions: list[str] = []
    if not active:
        if unique_sources >= 2:
            actions.append("enqueue_jit_synthesis")
        else:
            actions.append("wait_for_more_sources")
        return actions

    meta = build_synthesis_meta(active, lang=active.get("lang") or "sr")
    if meta.get("needs_upgrade"):
        actions.append("run_full_synthesis_upgrade")
    if freshness.get("refresh_needed"):
        actions.append("refresh_stale_synthesis")
    if pending_upgrade:
        actions.append("fast_upgrade_scheduled")
    if stuck:
        actions.append("force_stuck_fast_upgrade")
    if (active.get("quality_score") or 0) and float(active.get("quality_score") or 0) < 0.75:
        actions.append("refresh_low_score_synthesis")
    if not actions:
        actions.append("ok")
    return actions
