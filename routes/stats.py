import logging
import asyncio
import re
from pydantic import BaseModel
from typing import Optional, Any, Dict
from collections import defaultdict
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse

from database import db_manager as db
from utils import (
    cached_response, set_cache, score_cluster, rank_articles_in_cluster,
    calculate_reading_time, is_balanced, build_editor_analytics_payload,
    redis_client,
    build_source_reputation_rows
)
from health import get_source_statuses, reset_source_policy
from config import BREAKING_SCORE_THRESHOLD, SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY
from .common import _source_admin_authorized, _error_json
from .security import validate_date, validate_string_param, validate_email

log = logging.getLogger("presek")
router = APIRouter()

class QuoteOfTheDay(BaseModel):
    quote: str
    summary: Optional[str] = None
    generated_article: Optional[str] = None
    cluster_id: Optional[str] = None
    title: Optional[str] = None

class StatsSummaryResponse(BaseModel):
    status: str
    last_24h: int
    last_1h: int
    total_feeds: int
    total_clusters: int
    quote_of_the_day: Optional[QuoteOfTheDay] = None
    intelligence: Dict[str, Any]

_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"

def _pick_quote_of_the_day(row) -> dict | None:
    if not row:
        return None

    def _extract_text(value) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        for line in text.splitlines():
            # Strip list markers and extra whitespace
            clean = re.sub(r"^[-•*]\s*", "", line).strip()
            if not clean:
                continue
            
            # Remove citation markers like [1], [12], [6]
            clean = re.sub(r"\[\d+\]", "", clean).strip()
            
            # Remove redundant nested quotes at start/end
            clean = clean.strip("„“\"\'")
            
            if clean:
                return clean[:280]
        return ""

    quote = _extract_text(row.get("quote"))
    if not quote:
        quote = _extract_text(row.get("summary"))
    if not quote:
        quote = _extract_text(row.get("generated_article"))
    if not quote:
        return None

    return {
        "quote": quote,
        "cluster_id": row.get("cluster_id"),
        "title": row.get("title"),
    }

# Removed get_briefing route


@router.get("/archive/heatmap")
async def get_archive_heatmap():
    cache_key = "archive:heatmap:v2"
    cached = cached_response(cache_key, ttl=3600)
    if cached: return {"status": "success", "data": cached}
    
    # Use articles table as source of truth for historical presence
    sql = """
        WITH daily_stats AS (
            SELECT 
                DATE(created_at) as day,
                cluster_id,
                COUNT(*) as source_count
            FROM articles
            WHERE created_at >= NOW() - INTERVAL '90 days'
            GROUP BY day, cluster_id
        )
        SELECT 
            day,
            COUNT(DISTINCT cluster_id) as total_clusters,
            COUNT(DISTINCT cluster_id) FILTER (WHERE source_count >= 5) as breaking_clusters
        FROM daily_stats
        GROUP BY day
        ORDER BY day ASC
    """
    rows = await db.async_execute(sql)
    fmt = [{"day": r["day"].isoformat() if hasattr(r["day"], "isoformat") else str(r["day"]), "total_clusters": r["total_clusters"], "breaking_clusters": r["breaking_clusters"]} for r in rows]
    set_cache(cache_key, fmt, ttl=3600)
    return {"status": "success", "data": fmt}

@router.get("/archive")
async def get_archive(date: str = Query(...), source: str = "", topic: str = "", page: int = 0, page_size: int = 50):
    try:
        # Validate inputs
        validate_date(date)
        source = validate_string_param(source, "source", max_length=200, allow_empty=True)
        topic = validate_string_param(topic, "topic", max_length=200, allow_empty=True)
        
        if page < 0 or page > 1000:
            raise HTTPException(status_code=400, detail="Невалиден број на страница")
        if page_size < 1 or page_size > 50:
            raise HTTPException(status_code=400, detail="Невалидна големина на страница (1-50)")
        
        # Build parameterized query safely
        base_sql = "SELECT * FROM articles WHERE created_at::date = %s"
        params = [date]
        if source:
            base_sql += " AND source = %s"
            params.append(source)
        if topic:
            base_sql += " AND topic = %s"
            params.append(topic)
        base_sql += " ORDER BY created_at DESC LIMIT 1500"
        rows = await db.async_execute(base_sql, tuple(params))
        clusters = defaultdict(list)
        for r in rows:
            r["reading_time"] = calculate_reading_time(r.get("description", ""))
            clusters[r["cluster_id"]].append(r)
        ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        ranked.sort(key=score_cluster, reverse=True)
        offset = page * page_size
        paged = ranked[offset: offset + page_size]
        cids = [c[0]["cluster_id"] for c in paged]
        s_ids = set(await db.async_get_synthesis_ids(cids)) if cids else set()
        rep_images = {r["cluster_id"]: r["representative_image"] for r in await db.async_execute("SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)", (cids,))} if cids else {}
        payload = [{"cluster_id": c[0]["cluster_id"], "articles": c, "representative_image": rep_images.get(c[0]["cluster_id"]), "reading_time": c[0].get('reading_time', 1), "score": round(score_cluster(c), 3), "is_breaking": score_cluster(c) >= BREAKING_SCORE_THRESHOLD, "has_synthesis": c[0]["cluster_id"] in s_ids, "has_balanced": is_balanced(c)} for c in paged]
        
        # Build count queries safely
        count_sql = "SELECT COUNT(*) FROM articles WHERE created_at::date = %s"
        count_params = [date]
        if source:
            count_sql += " AND source = %s"
            count_params.append(source)
        if topic:
            count_sql += " AND topic = %s"
            count_params.append(topic)
        
        dist_source_sql = "SELECT COUNT(DISTINCT source) FROM articles WHERE created_at::date = %s"
        dist_source_params = [date]
        if source:
            dist_source_sql += " AND source = %s"
            dist_source_params.append(source)
        if topic:
            dist_source_sql += " AND topic = %s"
            dist_source_params.append(topic)
        
        group_source_sql = "SELECT source, COUNT(*) AS n FROM articles WHERE created_at::date = %s"
        group_source_params = [date]
        if source:
            group_source_sql += " AND source = %s"
            group_source_params.append(source)
        if topic:
            group_source_sql += " AND topic = %s"
            group_source_params.append(topic)
        group_source_sql += " GROUP BY source ORDER BY n DESC LIMIT 8"
        
        group_topic_sql = "SELECT topic, COUNT(*) AS n FROM articles WHERE created_at::date = %s"
        group_topic_params = [date]
        if source:
            group_topic_sql += " AND source = %s"
            group_topic_params.append(source)
        if topic:
            group_topic_sql += " AND topic = %s"
            group_topic_params.append(topic)
        group_topic_sql += " GROUP BY topic ORDER BY n DESC LIMIT 8"
        
        return {
            "clusters": payload, 
            "total": (await db.async_execute_one(count_sql, tuple(count_params)))["count"],
            "sources": (await db.async_execute_one(dist_source_sql, tuple(dist_source_params)))["count"],
            "date": date, "source": source, "topic": topic, "page": page, "page_size": page_size, 
            "has_more": offset + page_size < len(ranked), 
            "total_clusters": len(ranked),
            "top_sources": await db.async_execute(group_source_sql, tuple(group_source_params)),
            "top_topics": await db.async_execute(group_topic_sql, tuple(group_topic_params))
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Невалиден формат на датум. Користете YYYY-MM-DD")
    except Exception as e:
        log.error(f"Archive Error: {e}")
        raise HTTPException(status_code=500, detail="Неуспешно вчитување на архива")

@router.get("/stats")
async def get_stats_route():
    return {"status": "success", "data": await asyncio.to_thread(db.get_stats)}

@router.get("/stats/summary", response_model=StatsSummaryResponse)
async def get_stats_summary():
    cache_key = "api:stats:summary:v4"
    cached = cached_response(cache_key)
    if cached: return cached
    
    last_24h_res = await db.async_execute_one(f"SELECT COUNT(*) FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'")
    last_24h = last_24h_res["count"] if last_24h_res else 0
    
    last_1h_res = await db.async_execute_one(f"SELECT COUNT(*) FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '1 hour'")
    last_1h = last_1h_res["count"] if last_1h_res else 0
    total_feeds = (await db.async_execute_one("SELECT COUNT(*) FROM sources WHERE is_active = TRUE"))["count"] or 0
    quote_row = await db.async_execute_one("""
        SELECT s.quote, s.summary, s.generated_article, s.cluster_id,
               (SELECT title FROM articles WHERE cluster_id = s.cluster_id ORDER BY created_at DESC LIMIT 1) as title
        FROM cluster_summaries s
        WHERE s.created_at >= NOW() - INTERVAL '72 hours'
          AND (
              COALESCE(s.quote, '') != ''
              OR COALESCE(s.summary, '') != ''
              OR COALESCE(s.generated_article, '') != ''
          )
        ORDER BY
            CASE WHEN COALESCE(s.quote, '') != '' THEN 0 ELSE 1 END,
            s.created_at DESC
        LIMIT 1
    """)
    quote = _pick_quote_of_the_day(quote_row)
    
    from .common import build_intelligence_summary_payload
    intelligence = await build_intelligence_summary_payload(last_24h)
    
    res = {
        "status": "success",
        "last_24h": last_24h,
        "last_1h": last_1h,
        "total_feeds": total_feeds,
        "total_articles": last_24h,
        "total_clusters": intelligence["pluralism"]["total_clusters"],
        "quote_of_the_day": quote,
        "intelligence": intelligence,
    }
    set_cache(cache_key, res, ttl=300)
    return res

@router.post("/newsletter/subscribe")
async def subscribe_newsletter(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Невалиден JSON")
    email = validate_email(body.get("email", ""), "email")
    try:
        await db.async_execute("INSERT INTO subscribers (email) VALUES (%s) ON CONFLICT (email) DO UPDATE SET is_active = TRUE", (email,), fetch=False)
    except Exception as e:
        log.warning(f"[subscribe] DB error: {e}")
        return {"status": "error", "message": "Грешка при зачувување. Обидете се подоцна."}
    return {"status": "success", "message": "Успешно се пријавивте!"}

@router.get("/newsletter/unsubscribe")
async def unsubscribe_newsletter(email: str):
    try:
        await db.async_execute("UPDATE subscribers SET is_active = FALSE WHERE email = %s", (email,), fetch=False)
    except Exception as e:
        log.warning(f"[unsubscribe] DB error: {e}")
        return HTMLResponse(content="<h1>Грешка при одјавување.</h1>", status_code=500)
    return HTMLResponse(content="<h1>Успешно се одјавивте од билтенот на Пресек.</h1>")

@router.get("/stats/full")
async def get_stats_full(request: Request):
    if not _source_admin_authorized(request): raise HTTPException(status_code=403, detail="Забрането")
    cached = cached_response("stats:full", ttl=120)
    if cached: return cached

    lock_key = "lock:stats_full_generation"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=30):
            return JSONResponse(status_code=429, content={"message": "Статистиката се генерира, обидете се повторно за кратко."})
    except Exception as e:
        log.warning(f"Redis lock check failed for stats: {e}")

    try:
        last_24h = (await db.async_execute_one(f"SELECT COUNT(*) FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'"))["count"] or 0
        db_size_res = await db.async_execute_one("SELECT ROUND(pg_database_size(current_database()) / 1048576.0, 1) AS mb")
        db_size = float(db_size_res["mb"]) if db_size_res else 0.0
        dates = await db.async_execute_one("SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest FROM articles")
        
        profile_stats = await db.async_execute_one("SELECT COUNT(*) AS synced_profiles, COUNT(*) FILTER (WHERE updated_at >= NOW() - INTERVAL '7 days') AS active_profiles_7d, COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'recentClusters', '[]'::jsonb)) > 0) AS profiles_with_recent_reads, COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) > 0) AS profiles_following_topics, COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedSources', '[]'::jsonb)) > 0) AS profiles_following_sources FROM synced_reader_profiles") or {}
        delivery_stats = await db.async_execute_one("SELECT COUNT(*) FILTER (WHERE is_active = TRUE) AS delivery_active, COUNT(*) FILTER (WHERE COALESCE(target, '') != '') AS delivery_targets, COUNT(*) FILTER (WHERE morning_briefing = TRUE) AS morning_briefings, COUNT(*) FILTER (WHERE weekly_digest = TRUE) AS weekly_digests, COUNT(*) FILTER (WHERE breaking_topics = TRUE) AS breaking_topic_alerts, COUNT(*) FILTER (WHERE breaking_sources = TRUE) AS breaking_source_alerts FROM synced_delivery_subscriptions") or {}
        tracking_stats = await db.async_execute_one("SELECT COUNT(*) FILTER (WHERE event_type = 'send') AS sends_7d, COUNT(*) FILTER (WHERE event_type = 'open') AS opens_7d, COUNT(*) FILTER (WHERE event_type = 'click') AS clicks_7d FROM delivery_tracking_events WHERE created_at >= NOW() - INTERVAL '7 days'") or {}

        from .common import build_intelligence_summary_payload
        res = {
            "total_articles": (await db.async_execute_one("SELECT COUNT(*) FROM articles"))["count"] or 0,
            "last_24h": last_24h,
            "db_size_mb": db_size,
            "total_feeds": (await db.async_execute_one("SELECT COUNT(DISTINCT source) AS n FROM articles"))["n"] or 0,
            "intelligence": await build_intelligence_summary_payload(last_24h),
            "oldest_article": dates["oldest"] if dates else None,
            "new_article": dates["newest"] if dates else None,
            "by_source": await db.async_execute(f"SELECT source, COUNT(*) AS n FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY source ORDER BY n DESC LIMIT 10"),
            "by_category": [{"category": r["category"] or "Друго", "n": r["n"]} for r in await db.async_execute("SELECT category, COUNT(*) AS n FROM articles GROUP BY category ORDER BY n DESC LIMIT 8")],
            "velocity": [{"t": r["t"], "n": r["n"]} for r in await db.async_execute(f"SELECT date_trunc('hour', {_FRESHNESS_EXPR}) AS t, COUNT(*) AS n FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY t ORDER BY t")],
            "speed_leaderboard": await db.async_execute(f"SELECT source, COUNT(*) AS first_count FROM (SELECT DISTINCT ON (cluster_id) cluster_id, source FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '7 days' ORDER BY cluster_id, {_FRESHNESS_EXPR} ASC, created_at ASC) first_articles GROUP BY source ORDER BY first_count DESC LIMIT 8"),
            "editor_analytics": build_editor_analytics_payload(profile_stats, delivery_stats, await db.async_execute("SELECT value AS topic, COUNT(*) AS followers FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) AS value GROUP BY value ORDER BY followers DESC LIMIT 6"), await db.async_execute("SELECT value AS source, COUNT(*) AS followers FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedSources', '[]'::jsonb)) AS value GROUP BY value ORDER BY followers DESC LIMIT 6"), tracking_stats, await db.async_execute("SELECT delivery_kind, COUNT(*) FILTER (WHERE event_type = 'send') AS sends, COUNT(*) FILTER (WHERE event_type = 'open') AS opens, COUNT(*) FILTER (WHERE event_type = 'click') AS clicks FROM delivery_tracking_events WHERE created_at >= NOW() - INTERVAL '30 days' GROUP BY delivery_kind"), await db.async_execute("SELECT surface, COUNT(*) FILTER (WHERE event_type = 'impression') AS impressions, COUNT(*) FILTER (WHERE event_type = 'follow') AS follows, COUNT(*) FILTER (WHERE event_type = 'dismiss') AS dismissals, COUNT(*) FILTER (WHERE event_type = 'follow' AND suggestion_kind = 'topic') AS topic_follows, COUNT(*) FILTER (WHERE event_type = 'follow' AND suggestion_kind = 'source') AS source_follows FROM suggestion_surface_events WHERE created_at >= NOW() - INTERVAL '30 days' GROUP BY surface"), await db.async_execute("SELECT suggestion_kind, COUNT(*) FILTER (WHERE event_type = 'impression') AS impressions, COUNT(*) FILTER (WHERE event_type = 'follow') AS follows, COUNT(*) FILTER (WHERE event_type = 'dismiss') AS dismissals FROM suggestion_surface_events WHERE created_at >= NOW() - INTERVAL '30 days' AND COALESCE(suggestion_kind, '') != '' GROUP BY suggestion_kind"), await db.async_execute("SELECT surface, COUNT(*) FILTER (WHERE event_type = 'impression' AND created_at >= NOW() - INTERVAL '7 days') AS current_impressions, COUNT(*) FILTER (WHERE event_type = 'follow' AND created_at >= NOW() - INTERVAL '7 days') AS current_follows, COUNT(*) FILTER (WHERE event_type = 'dismiss' AND created_at >= NOW() - INTERVAL '7 days') AS current_dismissals FROM suggestion_surface_events WHERE created_at >= NOW() - INTERVAL '7 days' GROUP BY surface")),
        }
        set_cache("stats:full", res, ttl=120)
        return res
    except Exception as e:
        log.error(f"Full Stats Error: {e}")
        raise HTTPException(status_code=500, detail="Неуспешно генерирање на статистики")
    finally:
        try:
            redis_client.delete(lock_key)
        except Exception:
            pass

@router.get("/sources")
async def get_sources_route():
    rows = await db.async_execute("SELECT name, country, category, credibility, is_active, last_fetched, pause_mode, pause_reason, paused_at FROM sources ORDER BY is_active DESC, name ASC")
    pulse = await db.async_execute(f"SELECT source, COUNT(*) as count FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY source")
    speed = await db.async_execute(f"SELECT source, COUNT(*) AS first_count FROM (SELECT DISTINCT ON (cluster_id) cluster_id, source FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '7 days' ORDER BY cluster_id, {_FRESHNESS_EXPR} ASC, created_at ASC) first_articles GROUP BY source ORDER BY first_count DESC")
    history = await db.async_execute(f"WITH cluster_first AS (SELECT DISTINCT ON (cluster_id) cluster_id, source, {_FRESHNESS_EXPR} AS freshness_time FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '30 days' ORDER BY cluster_id, {_FRESHNESS_EXPR} ASC, created_at ASC), cluster_counts AS (SELECT cluster_id, COUNT(DISTINCT source) AS source_count FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '30 days' GROUP BY cluster_id), source_weeks AS (SELECT source, COUNT(*) FILTER (WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '7 days') AS recent_7d_volume, COUNT(*) FILTER (WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '14 days' AND {_FRESHNESS_EXPR} < NOW() - INTERVAL '7 days') AS previous_7d_volume FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '14 days' GROUP BY source) SELECT cf.source, COUNT(*) AS lead_count_30d, COUNT(*) FILTER (WHERE cc.source_count >= 2) AS corroborated_lead_count_30d, COUNT(*) FILTER (WHERE cc.source_count = 1) AS solo_lead_count_30d, COALESCE(sw.recent_7d_volume, 0) AS recent_7d_volume, COALESCE(sw.previous_7d_volume, 0) AS previous_7d_volume FROM cluster_first cf LEFT JOIN cluster_counts cc ON cc.cluster_id = cf.cluster_id LEFT JOIN source_weeks sw ON sw.source = cf.source GROUP BY cf.source, sw.recent_7d_volume, sw.previous_7d_volume")
    cats = await db.async_execute(f"SELECT source, category, COUNT(*) as count FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '30 days' AND category IS NOT NULL AND category != '' GROUP BY source, category ORDER BY source, count DESC")
    return build_source_reputation_rows(rows, pulse, speed, history, cats)

@router.post("/sources/{name}/control")
async def control_source_route(name: str, request: Request):
    if not _source_admin_authorized(request): return _error_json("Unauthorized", 403)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Невалиден JSON")
    action = str(payload.get("action", "")).strip().lower()
    source = await db.async_execute_one("SELECT credibility FROM sources WHERE name = %s", (name,))
    if not source: return _error_json("Source not found", 404)
    curr = float(source["credibility"])
    if action == "pause": await db.async_execute("UPDATE sources SET is_active=FALSE, pause_mode='manual', pause_reason='Manual', paused_at=NOW() WHERE name=%s", (name,), fetch=False)
    elif action == "resume": await db.async_execute("UPDATE sources SET is_active=TRUE, pause_mode=NULL, pause_reason=NULL, paused_at=NULL WHERE name=%s", (name,), fetch=False); reset_source_policy(name)
    elif action == "downrank": await db.async_execute("UPDATE sources SET credibility=%s WHERE name=%s", (max(0.4, curr-0.2), name), fetch=False)
    elif action == "uprank": await db.async_execute("UPDATE sources SET credibility=%s WHERE name=%s", (min(3.0, curr+0.2), name), fetch=False)
    elif action == "reset": await db.async_execute("UPDATE sources SET credibility=%s, pause_mode=NULL WHERE name=%s", (SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY), name), fetch=False); reset_source_policy(name)
    upd = await db.async_execute_one("SELECT * FROM sources WHERE name = %s", (name,))
    if upd: upd = dict(upd); upd["source_status"] = get_source_statuses().get(name)
    return {"status": "success", "source": upd}

@router.get("/stats/sentiment-trends")
async def get_sentiment_trends():
    """Returns average sentiment and tone analysis for the last 7 days."""
    cache_key = "api:stats:sentiment:trends:v1"
    cached = cached_response(cache_key, ttl=1800)
    if cached: return cached

    sql = """
        SELECT 
            DATE(created_at) as day,
            AVG((sentiment->'sentiment'->>'score')::float) as avg_score,
            AVG((sentiment->'tone_analysis'->>'objectivity')::float) as avg_objectivity,
            AVG((sentiment->'tone_analysis'->>'sensationalism')::float) as avg_sensationalism,
            COUNT(*) as cluster_count
        FROM cluster_summaries
        WHERE created_at >= NOW() - INTERVAL '7 days'
          AND sentiment IS NOT NULL
        GROUP BY day
        ORDER BY day ASC
    """
    try:
        rows = await db.async_execute(sql)
        data = []
        for r in rows:
            score = float(r["avg_score"] or 0)
            # Map score to label
            label = "неутрален"
            if score > 0.4: label = "позитивен"
            elif score > 0.1: label = "умерено позитивен"
            elif score < -0.4: label = "негативен"
            elif score < -0.1: label = "умерено негативен"

            data.append({
                "day": r["day"].isoformat() if hasattr(r["day"], "isoformat") else str(r["day"]),
                "score": round(score, 2),
                "label": label,
                "objectivity": round(float(r["avg_objectivity"] or 0), 2),
                "sensationalism": round(float(r["avg_sensationalism"] or 0), 2),
                "count": r["cluster_count"]
            })
        
        res = {"status": "success", "data": data}
        set_cache(cache_key, res, ttl=1800)
        return res
    except Exception as e:
        log.error(f"Sentiment Trends Error: {e}")
        return {"status": "error", "message": "Неуспешно вчитување на сентимент"}

@router.get("/stats/mood")
async def get_current_mood():
    """Returns a real-time 'National Mood' based on today's coverage."""
    cache_key = "api:stats:mood:v1"
    cached = cached_response(cache_key, ttl=600)
    if cached: return cached

    sql = """
        SELECT 
            sentiment->'sentiment'->>'tone' as tone,
            (sentiment->'sentiment'->>'score')::float as score,
            (sentiment->'tone_analysis'->>'objectivity')::float as objectivity
        FROM cluster_summaries
        WHERE created_at >= NOW() - INTERVAL '24 hours'
          AND sentiment IS NOT NULL
    """
    try:
        rows = await db.async_execute(sql)
        if not rows:
            return {"status": "success", "mood": "неутрален", "score": 0, "objectivity": 1.0}
        
        valid_scores = [r["score"] for r in rows if r["score"] is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
        
        valid_objs = [r["objectivity"] for r in rows if r["objectivity"] is not None]
        avg_obj = sum(valid_objs) / len(valid_objs) if valid_objs else 1.0
        
        # Dominant tone (most frequent)
        tones = [r["tone"] for r in rows if r["tone"]]
        dominant_tone = max(set(tones), key=tones.count) if tones else "неутрален"

        res = {
            "status": "success",
            "mood": dominant_tone,
            "score": round(avg_score, 2),
            "objectivity": round(avg_obj, 2),
            "sample_size": len(rows)
        }
        set_cache(cache_key, res, ttl=600)
        return res
    except Exception as e:
        log.error(f"Mood Error: {e}")
        return {"status": "error", "mood": "неутрален"}

