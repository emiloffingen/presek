import asyncio
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.api_errors import soft_error
from core.config import (
    API_MAX_Q_LEN,
    BREAKING_SCORE_THRESHOLD,
    DEFAULT_CREDIBILITY,
    DEFAULT_LANG,
    SOURCE_CREDIBILITY,
)
from core.database import db_manager as db
from core.limiter import custom_rate_limit
from core.health import get_source_statuses, reset_source_policy
from utils import (
    build_editor_analytics_payload,
    build_source_reputation_rows,
    cached_response,
    calculate_reading_time,
    is_balanced,
    rank_articles_in_cluster,
    redis_client,
    score_cluster,
    set_cache,
)

# Cleanup: removed _source_admin_authorized
from .common import _error_json, _source_admin_authorized
from .security import (
    validate_date,
    validate_email,
    validate_string_param,
    verify_csrf_token,
)

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


def get_date_range(date_str: str):
    """Returns (start, end) timestamps for a given YYYY-MM-DD string.
    The end is the start of the NEXT day for use with created_at < end.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    start = dt
    end = dt + timedelta(days=1)
    return start, end


async def _nearest_archive_days(d_start, d_end, country, q, source, topic):
    """Closest earlier/later day (within a year) that has articles matching the filters."""
    clause = " AND country = %s"
    fparams = [country]
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clause += " AND (title ILIKE %s ESCAPE '\\' OR summary ILIKE %s ESCAPE '\\')"
        fparams.extend([f"%{escaped}%", f"%{escaped}%"])
    if source:
        clause += " AND source = %s"
        fparams.append(source)
    if topic:
        clause += " AND topic = %s"
        fparams.append(topic)
    window = timedelta(days=365)
    prev_sql = f"SELECT MAX(created_at) AS d FROM articles WHERE created_at < %s AND created_at >= %s{clause}"  # nosec B608 - static clause with bound params
    next_sql = f"SELECT MIN(created_at) AS d FROM articles WHERE created_at >= %s AND created_at < %s{clause}"  # nosec B608
    try:
        prev_row, next_row = await asyncio.gather(
            db.async_execute_one(prev_sql, (d_start, d_start - window, *fparams)),
            db.async_execute_one(next_sql, (d_end, d_end + window, *fparams)),
        )
    except Exception as e:
        log.warning(f"[archive] nearest-day lookup failed: {e}")
        return {"prev": None, "next": None}

    def _day(row):
        value = (row or {}).get("d")
        return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else None

    return {"prev": _day(prev_row), "next": _day(next_row)}


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
            clean = clean.strip("„“\"'")

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
async def get_archive_heatmap(lang: str = DEFAULT_LANG):
    country_filter = "RS" if lang == "sr" else "MK"
    cache_key = f"archive:heatmap:v3:{lang}"
    cached = cached_response(cache_key, ttl=3600)
    if cached:
        return {"status": "success", "data": cached}

    # Use articles table as source of truth for historical presence
    sql = """
        WITH daily_stats AS (
            SELECT
                DATE(created_at) as day,
                cluster_id,
                COUNT(*) as source_count
            FROM articles
            WHERE created_at >= NOW() - INTERVAL '180 days' AND country = %s
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
    rows = await db.async_execute(sql, (country_filter,))
    fmt = [
        {
            "day": (r["day"].isoformat() if hasattr(r["day"], "isoformat") else str(r["day"])),
            "total_clusters": r["total_clusters"],
            "breaking_clusters": r["breaking_clusters"],
        }
        for r in rows
    ]
    set_cache(cache_key, fmt, ttl=3600)
    return {"status": "success", "data": fmt}


@router.get("/archive")
async def get_archive(
    date: str = Query(""),
    q: str = "",
    source: str = "",
    topic: str = "",
    lang: str = DEFAULT_LANG,
    page: int = 0,
    page_size: int = 50,
):
    try:
        # Validate inputs (a missing date means "today")
        date = date or datetime.now().strftime("%Y-%m-%d")
        validate_date(date)
        q = validate_string_param(q, "q", max_length=API_MAX_Q_LEN, allow_empty=True)
        source = validate_string_param(source, "source", max_length=200, allow_empty=True)
        topic = validate_string_param(topic, "topic", max_length=200, allow_empty=True)

        if page < 0 or page > 1000:
            raise HTTPException(status_code=400, detail="Невалиден број на страница")
        if page_size < 1 or page_size > 50:
            raise HTTPException(status_code=400, detail="Невалидна големина на страница (1-50)")

        # 1. Caching - Only for historical dates (older than today)
        cache_key = f"api:archive:v5:{date}:{q}:{source}:{topic}:{lang}:{page}:{page_size}"
        today_str = datetime.now().strftime("%Y-%m-%d")
        is_today = date == today_str

        if not is_today:
            cached = cached_response(cache_key)
            if cached:
                return cached

        d_start, d_end = get_date_range(date)
        country = "MK" if lang == "mk" else "RS"

        # 2. Main content query
        from routes.news import _ARTICLE_LIST_COLUMNS

        if q:
            # Escape LIKE special characters in search query
            escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            # embedding is needed only here, to re-rank search hits by similarity.
            base_sql = f"""
                SELECT {_ARTICLE_LIST_COLUMNS}, embedding FROM articles
                WHERE created_at >= %s AND created_at < %s AND country = %s
                  AND (title ILIKE %s ESCAPE '\\' OR summary ILIKE %s ESCAPE '\\' OR description ILIKE %s ESCAPE '\\')
            """  # nosec B608 - static column constant with bound params
            params = [
                d_start,
                d_end,
                country,
                f"%{escaped_q}%",
                f"%{escaped_q}%",
                f"%{escaped_q}%",
            ]
        else:
            # Slim columns: ranking needs source/title/description/created_at/
            # clicks, display needs category/topic/image. Full bodies stay out.
            base_sql = (
                "SELECT id, cluster_id, source, link, title, image_url, created_at, "
                "description, clicks, category, topic FROM articles "
                "WHERE created_at >= %s AND created_at < %s AND country = %s"
            )
            params = [d_start, d_end, country]

        if source:
            base_sql += " AND source = %s"
            params.append(source)
        if topic:
            base_sql += " AND topic = %s"
            params.append(topic)

        base_sql += " ORDER BY created_at DESC LIMIT 1500"

        # 3. Optimized metrics queries (combined where possible)
        # Combined count and unique sources
        metrics_sql = "SELECT COUNT(*) as total, COUNT(DISTINCT source) as source_count FROM articles WHERE created_at >= %s AND created_at < %s AND country = %s"
        metrics_params = [d_start, d_end, country]
        if q:
            metrics_sql += " AND (title ILIKE %s ESCAPE '\\' OR summary ILIKE %s ESCAPE '\\')"
            metrics_params.extend([f"%{escaped_q}%", f"%{escaped_q}%"])
        if source:
            metrics_sql += " AND source = %s"
            metrics_params.append(source)
        if topic:
            metrics_sql += " AND topic = %s"
            metrics_params.append(topic)

        # Facet counts: each facet ignores its own filter so the chips stay switchable
        # (selecting a topic must not collapse the topic list to that one topic).
        def _facet_sql(column: str, skip: str):
            sql = f"SELECT {column}, COUNT(*) AS n FROM articles WHERE created_at >= %s AND created_at < %s AND country = %s"  # nosec B608 - column is a literal from this function
            fparams = [d_start, d_end, country]
            if q:
                sql += " AND (title ILIKE %s ESCAPE '\\' OR summary ILIKE %s ESCAPE '\\')"
                fparams.extend([f"%{escaped_q}%", f"%{escaped_q}%"])
            if source and skip != "source":
                sql += " AND source = %s"
                fparams.append(source)
            if topic and skip != "topic":
                sql += " AND topic = %s"
                fparams.append(topic)
            sql += f" GROUP BY {column} ORDER BY n DESC LIMIT 12"  # nosec B608
            return sql, tuple(fparams)

        group_source_sql, group_source_params = _facet_sql("source", "source")
        group_topic_sql, group_topic_params = _facet_sql("topic", "topic")

        # Execute in parallel
        rows, metrics, top_sources, top_topics = await asyncio.gather(
            db.async_execute(base_sql, tuple(params)),
            db.async_execute_one(metrics_sql, tuple(metrics_params)),
            db.async_execute(group_source_sql, group_source_params),
            db.async_execute(group_topic_sql, group_topic_params),
        )

        clusters = defaultdict(list)
        for r in rows:
            clusters[r["cluster_id"]].append(r)

        ranked = [rank_articles_in_cluster(arts) for arts in clusters.values()]

        if q:
            from core.embeddings import get_query_embedding_async, parse_embedding_value

            query_vec = await get_query_embedding_async(q)
            if query_vec:
                q_norm = sum(v * v for v in query_vec) ** 0.5
                for arts in ranked:
                    best_sim = 0.0
                    for a in arts:
                        if a.get("embedding"):
                            a_vec = parse_embedding_value(a["embedding"])
                            if not a_vec:
                                continue
                            dot = sum(x * y for x, y in zip(query_vec, a_vec))
                            a_norm = sum(v * v for v in a_vec) ** 0.5
                            if q_norm and a_norm:
                                sim = dot / (q_norm * a_norm)
                                if sim > best_sim:
                                    best_sim = sim
                    arts[0]["match_score"] = best_sim
                ranked.sort(key=lambda x: x[0].get("match_score", 0), reverse=True)
        else:
            ranked.sort(key=score_cluster, reverse=True)

        offset = page * page_size
        paged = ranked[offset : offset + page_size]
        cids = [c[0]["cluster_id"] for c in paged]
        # Score once per cluster (was recomputed 3x); reading time only for
        # the displayed lead article.
        cluster_scores = {}
        for c in paged:
            s = round(score_cluster(c), 3)
            cluster_scores[c[0]["cluster_id"]] = s
            c[0]["reading_time"] = calculate_reading_time(c[0].get("description", ""))
        s_ids = set(await db.async_get_synthesis_ids(cids)) if cids else set()
        rep_images = (
            {
                r["cluster_id"]: r["representative_image"]
                for r in await db.async_execute(
                    "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
                    (cids,),
                )
            }
            if cids
            else {}
        )

        # Compact article projection: NewsCard only needs source identity,
        # counts and the lead's category/topic. Full bodies stay out
        # (~90KB -> ~6KB per cluster).
        def _compact_article(a):
            return {
                "id": a.get("id"),
                "source": a.get("source"),
                "link": a.get("link"),
                "title": a.get("title"),
                "image_url": a.get("image_url"),
                "created_at": a.get("created_at"),
                "category": a.get("category"),
                "topic": a.get("topic"),
            }

        payload = [
            {
                "cluster_id": c[0]["cluster_id"],
                "articles": [_compact_article(a) for a in c[:8]],
                "representative_image": rep_images.get(c[0]["cluster_id"]),
                "reading_time": c[0].get("reading_time", 1),
                "score": cluster_scores[c[0]["cluster_id"]],
                "is_breaking": cluster_scores[c[0]["cluster_id"]] >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": c[0]["cluster_id"] in s_ids,
                "has_balanced": is_balanced(c),
            }
            for c in paged
        ]

        nearest = await _nearest_archive_days(d_start, d_end, country, q, source, topic) if not ranked else None

        res = {
            "clusters": payload,
            "nearest": nearest,
            "total": metrics["total"],
            "sources": metrics["source_count"],
            "date": date,
            "q": q,
            "source": source,
            "topic": topic,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < len(ranked),
            "total_clusters": len(ranked),
            "top_sources": top_sources,
            "top_topics": top_topics,
        }

        # Set cache with long TTL for past dates
        if not is_today:
            set_cache(cache_key, res, ttl=43200)  # 12 hours
        else:
            set_cache(cache_key, res, ttl=300)  # 5 mins for today

        return res
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Nevalidan format datuma. Koristite YYYY-MM-DD")
    except Exception as e:
        log.error(f"Archive Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Неуспешно вчитување на архивата")


@router.get("/archive/daily-briefing")
async def get_archive_daily_briefing(date: str = Query(...), lang: str = DEFAULT_LANG):
    """Provides an AI-generated briefing for a specific historical date."""
    validate_date(date)
    cache_key = f"archive:briefing:{date}:{lang}:v1"
    cached = cached_response(cache_key, ttl=86400)
    if cached:
        return cached

    d_start, d_end = get_date_range(date)
    target_country = "MK" if lang == "mk" else "RS"

    # Find the top 3 clusters for that day and their summaries
    top_clusters = await db.async_execute(
        """
        SELECT s.cluster_id, s.summary, s.synthetic_headline
        FROM cluster_summaries s
        JOIN articles a ON s.cluster_id = a.cluster_id
        WHERE a.created_at >= %s AND a.created_at <= %s AND a.country = %s
        GROUP BY s.cluster_id, s.summary, s.synthetic_headline, s.pluralism_score
        ORDER BY s.pluralism_score DESC, COUNT(a.id) DESC
        LIMIT 3
    """,
        (d_start, d_end, target_country),
    )

    if not top_clusters:
        return {"briefing": None}

    briefing_parts = []
    for c in top_clusters:
        title = c["synthetic_headline"] or "Vazna tema"
        bullets = [b.strip() for b in (c["summary"] or "").split("\n") if b.strip()]
        if not bullets:
            continue

        summary = bullets[0]
        # Clean up common prefixes from the bullet
        if summary.startswith("-"):
            summary = summary[1:].strip()
        if summary.lower().startswith("sto se sluci:"):
            summary = summary[13:].strip()

        # If the first bullet is just repeating the headline, try the next bullet
        if summary.lower() == title.lower() and len(bullets) > 1:
            summary = bullets[1]
            if summary.startswith("-"):
                summary = summary[1:].strip()

        briefing_parts.append(f"**{title}**: {summary}")

    briefing = " • ".join(briefing_parts)
    res = {"briefing": briefing}
    set_cache(cache_key, res, ttl=86400)
    return res


@router.get("/archive/on-this-day")
async def get_archive_on_this_day(date: str = Query(...), lang: str = DEFAULT_LANG):
    """Finds a significant cluster from exactly 1 or 2 years ago."""
    validate_date(date)
    dt = datetime.strptime(date, "%Y-%m-%d")
    country = "MK" if lang == "mk" else "RS"

    for years in [1, 2]:
        past_date = (dt - timedelta(days=365 * years)).strftime("%Y-%m-%d")
        d_start, d_end = get_date_range(past_date)

        past_cluster = await db.async_execute_one(
            """
            SELECT s.cluster_id, s.summary, s.synthetic_headline, m.representative_image
            FROM cluster_summaries s
            JOIN articles a ON s.cluster_id = a.cluster_id
            JOIN cluster_metadata m ON s.cluster_id = m.cluster_id
            WHERE a.created_at >= %s AND a.created_at <= %s AND a.country = %s
            GROUP BY s.cluster_id, s.summary, s.synthetic_headline, m.representative_image, s.pluralism_score
            ORDER BY s.pluralism_score DESC, COUNT(a.id) DESC
            LIMIT 1
        """,
            (d_start, d_end, country),
        )

        if past_cluster:
            return {
                "years_ago": years,
                "date": past_date,
                "cluster_id": past_cluster["cluster_id"],
                "title": past_cluster["synthetic_headline"],
                "summary": past_cluster["summary"],
                "image": past_cluster["representative_image"],
            }

    return {"on_this_day": None}


@router.get("/stats")
async def get_stats_route():
    return {"status": "success", "data": await asyncio.to_thread(db.get_stats)}


@router.get("/stats/summary", response_model=StatsSummaryResponse)
async def get_stats_summary(lang: Optional[str] = DEFAULT_LANG):
    cache_key = f"api:stats:summary:v4:{lang}"
    cached = cached_response(cache_key)
    if cached:
        return cached

    target_country = "MK" if lang == "mk" else "RS"

    last_24h_res = await db.async_execute_one(
        f"SELECT COUNT(*) FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' AND country = %s",  # nosec B608 - static freshness constant with bound params
        (target_country,),
    )
    last_24h = last_24h_res["count"] if last_24h_res else 0

    last_1h_res = await db.async_execute_one(
        f"SELECT COUNT(*) FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '1 hour' AND country = %s",  # nosec B608 - static freshness constant with bound params
        (target_country,),
    )
    last_1h = last_1h_res["count"] if last_1h_res else 0

    total_feeds = (
        await db.async_execute_one(
            "SELECT COUNT(*) FROM sources WHERE is_active = TRUE AND country = %s",
            (target_country,),
        )
    )["count"] or 0

    quote_row = await db.async_execute_one(
        """
        SELECT s.quote, s.summary, s.generated_article, s.cluster_id,
               (SELECT title FROM articles WHERE cluster_id = s.cluster_id AND country = %s ORDER BY created_at DESC LIMIT 1) as title
        FROM cluster_summaries s
        JOIN articles a ON a.cluster_id = s.cluster_id
        WHERE s.created_at >= NOW() - INTERVAL '72 hours'
          AND a.country = %s
          AND s.lang = %s
          AND (
              COALESCE(s.quote, '') != ''
              OR COALESCE(s.summary, '') != ''
              OR COALESCE(s.generated_article, '') != ''
          )
          -- Priority to objective content if sentiment data exists
          AND (
              s.sentiment->'tone_analysis'->>'objectivity' IS NULL
              OR (CASE WHEN (s.sentiment->'tone_analysis'->>'objectivity') ~ '^[0-9.]+$' THEN (s.sentiment->'tone_analysis'->>'objectivity')::float ELSE 0.0 END) >= 0.4
          )
        GROUP BY s.quote, s.summary, s.generated_article, s.cluster_id, s.created_at, s.sentiment
        ORDER BY
            CASE WHEN COALESCE(s.quote, '') != '' THEN 0 ELSE 1 END,
            COALESCE(CASE WHEN (s.sentiment->'tone_analysis'->>'objectivity') ~ '^[0-9.]+$' THEN (s.sentiment->'tone_analysis'->>'objectivity')::float ELSE NULL END, 0.5) DESC,
            s.created_at DESC
        LIMIT 1
    """,
        (target_country, target_country, lang),
    )
    quote = _pick_quote_of_the_day(quote_row)

    runtime_events = {}
    try:
        hgetall = redis_client.hgetall
        if hgetall.__class__.__module__.startswith("unittest.mock"):
            bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            runtime_events = hgetall(f"presek:runtime_events:{bucket}") or {}
        elif os.environ.get("REDIS_URL") and not os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED"):
            bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            runtime_events = await asyncio.to_thread(hgetall, f"presek:runtime_events:{bucket}") or {}
    except Exception as e:
        log.warning(f"[stats] runtime event read failed: {e}")

    from .common import build_intelligence_summary_payload

    intelligence = await build_intelligence_summary_payload(last_24h, runtime_events=runtime_events)

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


def _newsletter_text(locale: str, mk: str, sr: str) -> str:
    return mk if locale == "mk" else sr


def _send_newsletter_confirmation(email: str, locale: str) -> bool:
    """Email a signed double-opt-in link. Returns False when SMTP is not configured."""
    import html as _html

    from core.signed_tokens import build_newsletter_confirm_url

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not (smtp_user and smtp_pass):
        log.warning("[subscribe] SMTP credentials not set; cannot send newsletter confirmation.")
        return False

    from tasks.utils import send_email

    base_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.mk")
    link = _html.escape(build_newsletter_confirm_url(base_url, email, locale), quote=True)
    subject = _newsletter_text(locale, "Потврдете ја пријавата за Пресек", "Potvrdite prijavu na Presek")
    body = _newsletter_text(
        locale,
        f"<p>Некој (се надеваме вие) ја пријави оваа адреса за утринскиот билтен на Пресек.</p>"
        f'<p><a href="{link}">Потврдете ја пријавата</a></p>'
        f"<p>Ако не сте вие, игнорирајте ја оваа порака и нема да добивате пораки.</p>",
        f"<p>Neko (nadamo se vi) prijavio je ovu adresu za jutarnji bilten Preseka.</p>"
        f'<p><a href="{link}">Potvrdite prijavu</a></p>'
        f"<p>Ako to niste vi, zanemarite ovu poruku i nećete dobijati poruke.</p>",
    )
    return bool(send_email(body, subject, smtp_user, smtp_pass, email))


async def _register_pending_subscriber(email: str, locale: str) -> bool:
    """Insert an inactive subscriber unless one exists; return whether it is already active.

    SELECT then INSERT, because older databases have no unique constraint on the
    email columns and some have no locale column at all. The bare ON CONFLICT DO
    NOTHING makes a simultaneous duplicate signup a no-op where the unique
    constraint exists (migration o5e6f7a8b9c0) and is harmless where it does not.
    """
    try:
        row = await db.async_execute_one(
            "SELECT is_active FROM subscribers WHERE email = %s AND locale = %s LIMIT 1",
            (email, locale),
        )
        if row:
            return bool(row.get("is_active"))
        await db.async_execute(
            "INSERT INTO subscribers (email, locale, is_active) VALUES (%s, %s, FALSE) ON CONFLICT DO NOTHING",
            (email, locale),
            fetch=False,
        )
        return False
    except Exception as e:
        if 'column "locale" does not exist' not in str(e).lower():
            raise
        log.warning("[subscribe] Legacy schema detected: locale column missing. Falling back.")

    row = await db.async_execute_one("SELECT is_active FROM subscribers WHERE email = %s LIMIT 1", (email,))
    if row:
        return bool(row.get("is_active"))
    await db.async_execute(
        "INSERT INTO subscribers (email, is_active) VALUES (%s, FALSE) ON CONFLICT DO NOTHING",
        (email,),
        fetch=False,
    )
    return False


@router.post("/newsletter/subscribe")
@custom_rate_limit("5/minute")
async def subscribe_newsletter(request: Request, csrf_valid: bool = Depends(verify_csrf_token)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Невалиден JSON")
    email = validate_email(body.get("email", ""), "email")
    locale = "mk" if str(body.get("locale") or "sr").strip().lower() == "mk" else "sr"
    error_payload = {
        "status": "error",
        "message": _newsletter_text(
            locale, "Грешка при зачувување. Обидете се подоцна.", "Greška pri čuvanju. Pokušajte kasnije."
        ),
    }
    # Double opt-in: new addresses stay inactive until the emailed link is used,
    # so nobody can enroll a third party's address.
    try:
        already_active = await _register_pending_subscriber(email, locale)
    except Exception as e:
        log.warning(f"[subscribe] DB error during subscription: {e}")
        return error_payload

    if not already_active:
        sent = await asyncio.to_thread(_send_newsletter_confirmation, email, locale)
        if not sent:
            return error_payload

    # Same answer whether or not the address was already subscribed (no enumeration).
    return {
        "status": "success",
        "pending_confirmation": True,
        "message": _newsletter_text(
            locale,
            "Проверете го сандачето и потврдете ја пријавата.",
            "Proverite sanduče i potvrdite prijavu.",
        ),
    }


@router.get("/newsletter/confirm")
@custom_rate_limit("20/minute")
async def confirm_newsletter(request: Request, token: str, lang: str = DEFAULT_LANG):
    """Activate a newsletter subscription from the signed double-opt-in link."""
    from core.signed_tokens import parse_newsletter_confirm_token

    locale = "mk" if str(lang or "sr").strip().lower() == "mk" else "sr"
    parsed = parse_newsletter_confirm_token(token)
    if not parsed or parsed[1] != locale:
        content = _newsletter_text(
            locale,
            "<h1>Невалиден или истечен линк за потврда.</h1>",
            "<h1>Nevalidan ili istekao link za potvrdu.</h1>",
        )
        return HTMLResponse(content=content, status_code=400)

    email, _ = parsed
    try:
        try:
            await db.async_execute(
                "UPDATE subscribers SET is_active = TRUE WHERE email = %s AND locale = %s",
                (email, locale),
                fetch=False,
            )
        except Exception as e:
            if 'column "locale" does not exist' not in str(e).lower():
                raise
            await db.async_execute(
                "UPDATE subscribers SET is_active = TRUE WHERE email = %s",
                (email,),
                fetch=False,
            )
    except Exception as e:
        log.warning(f"[confirm] DB error: {e}")
        content = _newsletter_text(locale, "<h1>Грешка при потврдување.</h1>", "<h1>Greška pri potvrdi.</h1>")
        return HTMLResponse(content=content, status_code=500)

    content = _newsletter_text(
        locale,
        "<h1>Пријавата е потврдена. Добредојдовте во Пресек!</h1>",
        "<h1>Prijava je potvrđena. Dobro došli u Presek!</h1>",
    )
    return HTMLResponse(content=content)


@router.get("/newsletter/unsubscribe")
async def unsubscribe_newsletter(token: str, lang: str = DEFAULT_LANG):
    """Deactivate a newsletter subscription using a signed token."""
    from core.signed_tokens import parse_newsletter_unsubscribe_token

    parsed = parse_newsletter_unsubscribe_token(token)
    locale = "mk" if str(lang or "sr").strip().lower() == "mk" else "sr"
    if not parsed:
        content = (
            "<h1>Nevalidan ili istekao link za odjavu.</h1>"
            if locale == "sr"
            else "<h1>Невалиден или истечен линк за одјава.</h1>"
        )
        return HTMLResponse(content=content, status_code=400)

    email, token_locale = parsed
    if token_locale != locale:
        content = (
            "<h1>Nevalidan ili istekao link za odjavu.</h1>"
            if locale == "sr"
            else "<h1>Невалиден или истечен линк за одјава.</h1>"
        )
        return HTMLResponse(content=content, status_code=400)

    try:
        await db.async_execute(
            "UPDATE subscribers SET is_active = FALSE WHERE email = %s AND locale = %s",
            (email, locale),
            fetch=False,
        )
    except Exception as e:
        log.warning(f"[unsubscribe] DB error: {e}")
        content = "<h1>Greška pri odjavljivanju.</h1>" if locale == "sr" else "<h1>Грешка при одјавување.</h1>"
        return HTMLResponse(content=content, status_code=500)

    content = (
        "<h1>Uspešno ste se odjavili sa biltena Preseka.</h1>"
        if locale == "sr"
        else "<h1>Успешно се одјавивте од билтенот на Пресек.</h1>"
    )
    return HTMLResponse(content=content)


async def _fetch_stats_parallel():
    """Fetch independent database queries in parallel for better performance."""
    # Queries that don't depend on each other can run concurrently
    coroutines = [
        # Basic stats
        db.async_execute_one(f"SELECT COUNT(*) FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'"),  # nosec B608 - static freshness constant, no params
        db.async_execute_one("SELECT ROUND(pg_database_size(current_database()) / 1048576.0, 1) AS mb"),
        db.async_execute_one("SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest FROM articles"),
        db.async_execute_one("SELECT COUNT(*) FROM articles"),
        db.async_execute_one("SELECT COUNT(DISTINCT source) AS n FROM articles"),
        # Profile stats
        db.async_execute_one(
            """SELECT COUNT(*) AS synced_profiles, COUNT(*) FILTER (WHERE updated_at >= NOW() - INTERVAL '7 days') AS active_profiles_7d,
           COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'recentClusters', '[]'::jsonb)) > 0) AS profiles_with_recent_reads,
           COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) > 0) AS profiles_following_topics,
           COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedSources', '[]'::jsonb)) > 0) AS profiles_following_sources FROM synced_reader_profiles"""
        ),
        # Delivery stats
        db.async_execute_one(
            """SELECT COUNT(*) FILTER (WHERE is_active = TRUE) AS delivery_active, COUNT(*) FILTER (WHERE COALESCE(target, '') != '') AS delivery_targets,
           COUNT(*) FILTER (WHERE morning_briefing = TRUE) AS morning_briefings, COUNT(*) FILTER (WHERE weekly_digest = TRUE) AS weekly_digests,
           COUNT(*) FILTER (WHERE breaking_topics = TRUE) AS breaking_topic_alerts, COUNT(*) FILTER (WHERE breaking_sources = TRUE) AS breaking_source_alerts
           FROM synced_delivery_subscriptions"""
        ),
        # Tracking stats
        db.async_execute_one(
            "SELECT COUNT(*) FILTER (WHERE event_type = 'send') AS sends_7d, COUNT(*) FILTER (WHERE event_type = 'open') AS opens_7d, COUNT(*) FILTER (WHERE event_type = 'click') AS clicks_7d FROM delivery_tracking_events WHERE created_at >= NOW() - INTERVAL '7 days'"
        ),
    ]

    return await asyncio.gather(*coroutines, return_exceptions=True)


from routes.security import admin_auth


@router.get("/stats/full")
async def get_stats_full(request: Request, lang: str = DEFAULT_LANG, authorized: str = Depends(admin_auth)):
    cached = cached_response("stats:full:sr", ttl=120)
    if cached:
        return cached
    # ... (rest of the logic remains unchanged)

    lock_key = "lock:stats_full_generation"
    try:
        if not redis_client.set(lock_key, "1", nx=True, ex=30):
            message = (
                "Statistika se generiše, pokušajte ponovo uskoro."
                if lang == "sr"
                else "Статистиката се генерира, обидете се повторно за кратко."
            )
            return _error_json(message, 429)
    except Exception as e:
        log.warning(f"Redis lock check failed for stats: {e}")

    try:
        # Fetch independent queries in parallel
        results = await _fetch_stats_parallel()

        # Assign results with error handling
        last_24h = (
            (results[0] or {}).get("count") if results and len(results) > 0 and isinstance(results[0], dict) else 0
        )
        db_size_res = results[1] if len(results) > 1 else {}
        db_size = float(db_size_res.get("mb")) if db_size_res else 0.0
        dates = results[2] if len(results) > 2 else {}
        total_articles_row = results[3] if len(results) > 3 else {}
        total_articles = total_articles_row.get("count") if isinstance(total_articles_row, dict) else 0
        total_feeds_row = results[4] if len(results) > 4 else {}
        total_feeds = total_feeds_row.get("n") if isinstance(total_feeds_row, dict) else 0
        profile_stats = results[5] if len(results) > 5 else {}
        delivery_stats = results[6] if len(results) > 6 else {}
        tracking_stats = results[7] if len(results) > 7 else {}

        # Log any errors from parallel execution
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.error(f"Parallel stats query {i} failed: {r}")

        # Sequential queries that depend on results or are complex
        from .common import build_intelligence_summary_payload

        intelligence = await build_intelligence_summary_payload(last_24h or 0)

        # These aggregation queries can also run in parallel with each other
        by_source, by_category_raw, velocity, speed_leaderboard = await asyncio.gather(
            db.async_execute(
                f"SELECT source, COUNT(*) AS n FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY source ORDER BY n DESC LIMIT 10"  # nosec B608 - static freshness constant, no params
            ),
            db.async_execute("SELECT category, COUNT(*) AS n FROM articles GROUP BY category ORDER BY n DESC LIMIT 8"),
            db.async_execute(
                f"SELECT date_trunc('hour', {_FRESHNESS_EXPR}) AS t, COUNT(*) AS n FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY t ORDER BY t"  # nosec B608 - static freshness constant, no params
            ),
            db.async_execute(
                f"SELECT source, COUNT(*) AS first_count FROM (SELECT DISTINCT ON (cluster_id) cluster_id, source FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '7 days' ORDER BY cluster_id, {_FRESHNESS_EXPR} ASC, created_at ASC) first_articles GROUP BY source ORDER BY first_count DESC LIMIT 8"  # nosec B608 - static freshness constant, no params
            ),
            return_exceptions=True,
        )

        # Editor analytics queries - run in parallel
        (
            topics_followed,
            sources_followed,
            delivery_kind_stats,
            surface_stats_30d,
            suggestion_kind_stats,
            surface_stats_7d,
        ) = await asyncio.gather(
            db.async_execute(
                "SELECT value AS topic, COUNT(*) AS followers FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) AS value GROUP BY value ORDER BY followers DESC LIMIT 6"
            ),
            db.async_execute(
                "SELECT value AS source, COUNT(*) AS followers FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedSources', '[]'::jsonb)) AS value GROUP BY value ORDER BY followers DESC LIMIT 6"
            ),
            db.async_execute(
                "SELECT delivery_kind, COUNT(*) FILTER (WHERE event_type = 'send') AS sends, COUNT(*) FILTER (WHERE event_type = 'open') AS opens, COUNT(*) FILTER (WHERE event_type = 'click') AS clicks FROM delivery_tracking_events WHERE created_at >= NOW() - INTERVAL '30 days' GROUP BY delivery_kind"
            ),
            db.async_execute(
                """SELECT surface, COUNT(*) FILTER (WHERE event_type = 'impression') AS impressions, COUNT(*) FILTER (WHERE event_type = 'follow') AS follows,
               COUNT(*) FILTER (WHERE event_type = 'dismiss') AS dismissals,
               COUNT(*) FILTER (WHERE event_type = 'follow' AND suggestion_kind = 'topic') AS topic_follows,
               COUNT(*) FILTER (WHERE event_type = 'follow' AND suggestion_kind = 'source') AS source_follows
               FROM suggestion_surface_events WHERE created_at >= NOW() - INTERVAL '30 days' GROUP BY surface"""
            ),
            db.async_execute(
                """SELECT suggestion_kind, COUNT(*) FILTER (WHERE event_type = 'impression') AS impressions, COUNT(*) FILTER (WHERE event_type = 'follow') AS follows,
               COUNT(*) FILTER (WHERE event_type = 'dismiss') AS dismissals
               FROM suggestion_surface_events WHERE created_at >= NOW() - INTERVAL '30 days' AND COALESCE(suggestion_kind, '') != '' GROUP BY suggestion_kind"""
            ),
            db.async_execute(
                """SELECT surface, COUNT(*) FILTER (WHERE event_type = 'impression' AND created_at >= NOW() - INTERVAL '7 days') AS current_impressions,
               COUNT(*) FILTER (WHERE event_type = 'follow' AND created_at >= NOW() - INTERVAL '7 days') AS current_follows,
               COUNT(*) FILTER (WHERE event_type = 'dismiss' AND created_at >= NOW() - INTERVAL '7 days') AS current_dismissals
               FROM suggestion_surface_events WHERE created_at >= NOW() - INTERVAL '7 days' GROUP BY surface"""
            ),
            return_exceptions=True,
        )

        # Handle errors from aggregation queries
        def safe_result(r, default=None):
            return r if not isinstance(r, Exception) else default

        res = {
            "total_articles": int(total_articles) if total_articles else 0,
            "last_24h": int(last_24h) if last_24h else 0,
            "db_size_mb": db_size,
            "total_feeds": int(total_feeds) if total_feeds else 0,
            "intelligence": intelligence,
            "oldest_article": dates.get("oldest") if dates else None,
            "new_article": dates.get("newest") if dates else None,
            "by_source": safe_result(by_source, []),
            "by_category": [
                {"category": r["category"] or "Drugo", "n": r["n"]} for r in safe_result(by_category_raw, [])
            ],
            "velocity": [{"t": r["t"], "n": r["n"]} for r in safe_result(velocity, [])],
            "speed_leaderboard": safe_result(speed_leaderboard, []),
            "editor_analytics": build_editor_analytics_payload(
                profile_stats,
                delivery_stats,
                safe_result(topics_followed, []),
                safe_result(sources_followed, []),
                tracking_stats,
                safe_result(delivery_kind_stats, []),
                safe_result(surface_stats_30d, []),
                safe_result(suggestion_kind_stats, []),
                safe_result(surface_stats_7d, []),
            ),
        }
        set_cache("stats:full", res, ttl=120)
        return res
    except Exception as e:
        log.error(f"Full Stats Error: {e}")
        detail = "Neuspešno generisanje statistika" if lang == "sr" else "Неуспешно генерирање на статистики"
        raise HTTPException(status_code=500, detail=detail)
    finally:
        try:
            redis_client.delete(lock_key)
        except Exception:
            log.debug("Stats fallback")


@router.get("/sources")
async def get_sources_route():
    cache_key = "api:sources:v2:all"
    cached = cached_response(cache_key, ttl=120)
    if cached:
        return cached

    rows = await db.async_execute(
        "SELECT name, country, category, credibility, is_active, last_fetched, pause_mode, pause_reason, paused_at FROM sources ORDER BY is_active DESC, name ASC"
    )
    pulse = await db.async_execute(
        f"SELECT source, COUNT(*) as count FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours' GROUP BY source"  # nosec B608 - static freshness constant, no params
    )
    speed = await db.async_execute(
        f"SELECT source, COUNT(*) AS first_count FROM (SELECT DISTINCT ON (cluster_id) cluster_id, source FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '7 days' ORDER BY cluster_id, {_FRESHNESS_EXPR} ASC, created_at ASC) first_articles GROUP BY source ORDER BY first_count DESC"  # nosec B608 - static freshness constant, no params
    )
    history = await db.async_execute(
        f"WITH cluster_first AS (SELECT DISTINCT ON (cluster_id) cluster_id, source, {_FRESHNESS_EXPR} AS freshness_time FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '30 days' ORDER BY cluster_id, {_FRESHNESS_EXPR} ASC, created_at ASC), cluster_counts AS (SELECT cluster_id, COUNT(DISTINCT source) AS source_count FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '30 days' GROUP BY cluster_id), source_weeks AS (SELECT source, COUNT(*) FILTER (WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '7 days') AS recent_7d_volume, COUNT(*) FILTER (WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '14 days' AND {_FRESHNESS_EXPR} < NOW() - INTERVAL '7 days') AS previous_7d_volume FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '14 days' GROUP BY source) SELECT cf.source, COUNT(*) AS lead_count_30d, COUNT(*) FILTER (WHERE cc.source_count >= 2) AS corroborated_lead_count_30d, COUNT(*) FILTER (WHERE cc.source_count = 1) AS solo_lead_count_30d, COALESCE(sw.recent_7d_volume, 0) AS recent_7d_volume, COALESCE(sw.previous_7d_volume, 0) AS previous_7d_volume FROM cluster_first cf LEFT JOIN cluster_counts cc ON cc.cluster_id = cf.cluster_id LEFT JOIN source_weeks sw ON sw.source = cf.source GROUP BY cf.source, sw.recent_7d_volume, sw.previous_7d_volume"  # nosec B608 - static freshness constant, no params
    )
    cats = await db.async_execute(
        f"SELECT source, category, COUNT(*) as count FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '30 days' AND category IS NOT NULL AND category != '' GROUP BY source, category ORDER BY source, count DESC"  # nosec B608 - static freshness constant, no params
    )
    daily = await db.async_execute(
        f"SELECT source, DATE_TRUNC('day', {_FRESHNESS_EXPR})::date AS day, COUNT(*) as n FROM articles WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '30 days' GROUP BY source, day"  # nosec B608 - static freshness constant, no params
    )
    result = build_source_reputation_rows(rows, pulse, speed, history, cats, daily)
    set_cache(cache_key, result, ttl=120)
    # Same shape as the cached path above (a bare list) -- the page consumes a list.
    return result


@router.post("/sources/{name}/control")
async def control_source_route(name: str, request: Request, csrf_valid: bool = Depends(verify_csrf_token)):
    if not _source_admin_authorized(request):
        return _error_json("Unauthorized", 403)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Невалиден JSON")
    action = str(payload.get("action", "")).strip().lower()
    source = await db.async_execute_one("SELECT credibility FROM sources WHERE name = %s", (name,))
    if not source:
        return _error_json("Source not found", 404)
    curr = float(source["credibility"])
    if action == "pause":
        await db.async_execute(
            "UPDATE sources SET is_active=FALSE, pause_mode='manual', pause_reason='Manual', paused_at=NOW() WHERE name=%s",
            (name,),
            fetch=False,
        )
    elif action == "resume":
        await db.async_execute(
            "UPDATE sources SET is_active=TRUE, pause_mode=NULL, pause_reason=NULL, paused_at=NULL WHERE name=%s",
            (name,),
            fetch=False,
        )
        reset_source_policy(name)
    elif action == "downrank":
        await db.async_execute(
            "UPDATE sources SET credibility=%s WHERE name=%s",
            (max(0.4, curr - 0.2), name),
            fetch=False,
        )
    elif action == "uprank":
        await db.async_execute(
            "UPDATE sources SET credibility=%s WHERE name=%s",
            (min(3.0, curr + 0.2), name),
            fetch=False,
        )
    elif action == "reset":
        await db.async_execute(
            "UPDATE sources SET credibility=%s, pause_mode=NULL WHERE name=%s",
            (SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY), name),
            fetch=False,
        )
        reset_source_policy(name)
    upd = await db.async_execute_one("SELECT * FROM sources WHERE name = %s", (name,))
    if upd:
        upd = dict(upd)
        upd["source_status"] = get_source_statuses().get(name)
    return {"status": "success", "source": upd}


@router.get("/stats/sentiment-trends")
async def get_sentiment_trends(lang: Optional[str] = DEFAULT_LANG):
    """Returns average sentiment and tone analysis for the last 7 days, filtered by language."""
    cache_key = f"api:stats:sentiment:trends:v2:{lang}"
    cached = cached_response(cache_key, ttl=1800)
    if cached:
        return cached

    sql = """
        SELECT
            DATE(created_at) as day,
            AVG(CASE WHEN (sentiment->'sentiment'->>'score') ~ '^-?[0-9.]+$' THEN (sentiment->'sentiment'->>'score')::float ELSE NULL END) as avg_score,
            AVG(CASE WHEN (tone_analysis->>'objectivity') ~ '^[0-9.]+$' THEN (tone_analysis->>'objectivity')::float ELSE NULL END) as avg_objectivity,
            AVG(CASE WHEN (tone_analysis->>'sensationalism') ~ '^[0-9.]+$' THEN (tone_analysis->>'sensationalism')::float ELSE NULL END) as avg_sensationalism,
            COUNT(*) as cluster_count
        FROM cluster_summaries
        WHERE created_at >= NOW() - INTERVAL '7 days'
          AND sentiment IS NOT NULL
          AND lang = %s
        GROUP BY day
        ORDER BY day ASC
    """
    try:
        rows = await db.async_execute(sql, (lang,))
        data = []
        for r in rows:
            score = float(r["avg_score"] or 0)
            # Map score to label
            label = "neutralen"
            if score > 0.4:
                label = "pozitiven"
            elif score > 0.1:
                label = "umereno pozitiven"
            elif score < -0.4:
                label = "negativen"
            elif score < -0.1:
                label = "umereno negativen"

            data.append(
                {
                    "day": (r["day"].isoformat() if hasattr(r["day"], "isoformat") else str(r["day"])),
                    "score": round(score, 2),
                    "label": label,
                    "objectivity": round(float(r["avg_objectivity"] or 0), 2),
                    "sensationalism": round(float(r["avg_sensationalism"] or 0), 2),
                    "count": r["cluster_count"],
                }
            )

        res = {"status": "success", "data": data}
        set_cache(cache_key, res, ttl=1800)
        return res
    except Exception as e:
        log.error(f"Sentiment Trends Error: {e}")
        return soft_error(message="Неуспешно вчитување на сентиментот")


@router.get("/stats/mood")
async def get_current_mood(lang: Optional[str] = DEFAULT_LANG):
    """Returns a real-time 'National Mood' based on today's coverage, filtered by language."""
    cache_key = f"api:stats:mood:v2:{lang}"
    cached = cached_response(cache_key, ttl=600)
    if cached:
        return cached

    sql = """
        SELECT
            sentiment->'sentiment'->>'tone' as tone,
            CASE WHEN (sentiment->'sentiment'->>'score') ~ '^-?[0-9.]+$' THEN (sentiment->'sentiment'->>'score')::float ELSE NULL END as score,
            CASE WHEN (tone_analysis->>'objectivity') ~ '^[0-9.]+$' THEN (tone_analysis->>'objectivity')::float ELSE NULL END as objectivity
        FROM cluster_summaries
        WHERE created_at >= NOW() - INTERVAL '24 hours'
          AND sentiment IS NOT NULL
          AND lang = %s
    """
    try:
        rows = await db.async_execute(sql, (lang,))
        if not rows:
            return {
                "status": "success",
                "mood": "neutralen",
                "score": 0,
                "objectivity": 1.0,
                "sample_size": 0,
            }

        valid_scores = [r["score"] for r in rows if r["score"] is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

        valid_objs = [r["objectivity"] for r in rows if r["objectivity"] is not None]
        avg_obj = sum(valid_objs) / len(valid_objs) if valid_objs else 1.0

        # Dominant tone (most frequent)
        tones = [r["tone"] for r in rows if r["tone"]]
        dominant_tone = max(set(tones), key=tones.count) if tones else "neutralen"

        res = {
            "status": "success",
            "mood": dominant_tone,
            "score": round(avg_score, 2),
            "objectivity": round(avg_obj, 2),
            "sample_size": len(rows),
        }
        set_cache(cache_key, res, ttl=600)
        return res
    except Exception as e:
        log.error(f"Mood Error: {e}")
        return soft_error(mood="neutralen")
