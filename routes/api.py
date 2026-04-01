from __future__ import annotations
import datetime
import json
import os
import re
import time
import logging
import urllib.request
import urllib.error
from collections import defaultdict

from flask import Blueprint, jsonify, request, Response
from database import db_manager as db
from ai_engine import _call_ai
from utils import score_cluster, rank_articles_in_cluster, cached_response, set_cache, calculate_reading_time, is_balanced
from config import BREAKING_SCORE_THRESHOLD
from embeddings import generate_query_embedding

api_bp = Blueprint('api', __name__)
log = logging.getLogger("presek")

MAX_PAGE = 1000
MAX_Q_LEN = 500

# Allowed image content types for proxy
_PROXY_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
_PROXY_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

def success_response(data, meta=None):
    return jsonify({
        "status": "success",
        "data": data,
        "meta": meta or {}
    })

def error_response(message, code=500, details=None):
    resp = {"status": "error", "message": message}
    if details:
        resp["details"] = details
    return jsonify(resp), code

@api_bp.route("/api/news")
def api_news():
    try:
        page      = min(max(0, request.args.get("page", 0, type=int)), MAX_PAGE)
        page_size = min(200, max(1, request.args.get("page_size", 50, type=int)))

        # Safety: prevent runaway OFFSET queries
        if page * page_size > 50000:
            return error_response("Page offset too large", 400)

        country   = request.args.get("country", "🇲🇰")

        # Handle double-encoding of emojis
        try:
            if country:
                country_bytes = country.encode('latin-1')
                if b'\xf0\x9f' in country_bytes:
                    country = country_bytes.decode('utf-8')
        except: pass

        sub       = request.args.get("sub", "").strip()
        ids       = request.args.get("ids", "").strip()
        sort_by   = request.args.get("sort", "recent")
        topic     = request.args.get("topic", "").strip()
        sentiment = request.args.get("sentiment", "").strip()
        q         = request.args.get("q", "").strip()[:MAX_Q_LEN]
        follow_sources = request.args.get("follow_sources", "").strip()
        follow_topics  = request.args.get("follow_topics", "").strip()

        cache_key = f"v4:news:{country}:{sub}:{ids}:{sort_by}:{topic}:{sentiment}:{follow_sources}:{follow_topics}:{q}:{page}:{page_size}"
        cached = cached_response(cache_key, ttl=30)
        if cached: return jsonify(cached)

        # DAL Extraction
        if ids:
            cluster_ids = [cid.strip() for cid in ids.split(',') if cid.strip()]
            rows = db.get_articles_by_ids(cluster_ids)
        elif q:
            # Semantic Upgrade: If query has more than 3 words, try semantic search
            if len(q.split()) >= 3:
                try:
                    emb = generate_query_embedding(q)
                    if emb:
                        rows = db.search_semantic(emb, limit=100)
                    else:
                        rows = db.search_articles(q)
                except Exception as e:
                    log.warning(f"Semantic search failed, falling back to keyword: {e}")
                    rows = db.search_articles(q)
            else:
                rows = db.search_articles(q)
        elif follow_sources or follow_topics:
            sources_list = [s.strip() for s in follow_sources.split(',') if s.strip()]
            topics_list = [t.strip() for t in follow_topics.split(',') if t.strip()]
            rows = db.get_personalized_articles(sources_list, topics_list)
        else:
            rows = db.get_articles_by_country(country, sub=sub, topic=topic, sentiment=sentiment)

        # Logic Layer: Grouping & Scoring
        clusters = defaultdict(list)
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            clusters[r['cluster_id']].append(r)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]

        if sort_by == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster, reverse=True)

        # Pagination & Meta
        start = page * page_size
        end = start + page_size
        paged_clusters = ranked_clusters[start:end]

        synthesis_ids = db.get_synthesis_ids([c[0]["cluster_id"] for c in paged_clusters])

        result = []
        for arts in paged_clusters:
            s = score_cluster(arts)
            cid = arts[0]["cluster_id"]
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "score": round(s, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts)
            })

        response_data = {
            "clusters": result,
            "has_more": end < len(ranked_clusters),
            "total_clusters": len(ranked_clusters)
        }

        final_json = {
            "status": "success",
            "page": page,
            "page_size": page_size,
            **response_data
        }

        set_cache(cache_key, final_json, ttl=60)
        return jsonify(final_json)

    except Exception as e:
        log.error(f"[api/news] Error: {e}", exc_info=True)
        return error_response("Failed to fetch news")

@api_bp.route("/api/stats")
def api_stats():
    try:
        return success_response(db.get_stats())
    except Exception as e:
        log.error(f"[api/stats] Error: {e}", exc_info=True)
        return error_response("Failed to fetch stats")

@api_bp.route("/api/stats/full")
def api_stats_full():
    try:
        cached = cached_response("stats:full", ttl=120)
        if cached:
            return jsonify(cached)

        total = db.execute_one("SELECT COUNT(*) FROM articles")["count"] or 0
        last_24h = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )["count"] or 0
        summarized = db.execute_one(
            "SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''"
        )["count"] or 0
        summarized_pct = round((summarized / total * 100), 1) if total else 0

        db_size_row = db.execute_one(
            "SELECT ROUND(pg_database_size(current_database()) / 1048576.0, 1) AS mb"
        )
        db_size_mb = float(db_size_row["mb"]) if db_size_row else 0

        total_feeds = db.execute_one(
            "SELECT COUNT(DISTINCT source) AS n FROM articles"
        )["n"] or 0

        dates_row = db.execute_one(
            "SELECT MIN(created_at) AS oldest, MAX(created_at) AS newest FROM articles"
        )
        oldest_article = dates_row["oldest"].isoformat() if dates_row and dates_row["oldest"] else None
        newest_article = dates_row["newest"].isoformat() if dates_row and dates_row["newest"] else None

        by_source = db.execute(
            "SELECT source, COUNT(*) AS n FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "AND (country = '🇲🇰' OR country IS NULL OR country = '') "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )

        by_category = [
            {"cat": r["category"] or "Друго", "n": r["n"]}
            for r in db.execute(
                "SELECT category, COUNT(*) AS n FROM articles GROUP BY category ORDER BY n DESC LIMIT 8"
            )
        ]

        velocity = db.execute(
            "SELECT date_trunc('hour', created_at) AS t, COUNT(*) AS n "
            "FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY t ORDER BY t"
        )
        velocity_out = [{"t": r["t"].isoformat(), "n": r["n"]} for r in velocity]

        speed_leaderboard = db.execute(
            "SELECT source, COUNT(*) AS first_count FROM ("
            "  SELECT DISTINCT ON (cluster_id) cluster_id, source "
            "  FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' "
            "  AND (country = '🇲🇰' OR country IS NULL OR country = '') "
            "  ORDER BY cluster_id, created_at ASC"
            ") first_articles GROUP BY source ORDER BY first_count DESC LIMIT 8"
        )

        result = {
            "total_articles": total,
            "last_24h": last_24h,
            "summarized_pct": summarized_pct,
            "uptime": "Online",
            "db_size_mb": db_size_mb,
            "total_feeds": total_feeds,
            "oldest_article": oldest_article,
            "new_article": newest_article,
            "by_source": [{"source": r["source"], "n": r["n"]} for r in by_source],
            "by_category": by_category,
            "velocity": velocity_out,
            "speed_leaderboard": [{"source": r["source"], "first_count": r["first_count"]} for r in speed_leaderboard],
            "sentiment_index": []
        }

        set_cache("stats:full", result, ttl=120)
        return jsonify(result)

    except Exception as e:
        log.error(f"[api/stats/full] Error: {e}", exc_info=True)
        return error_response("Failed to fetch stats")

@api_bp.route("/api/briefing")
def api_briefing():
    try:
        row = db.execute_one(
            "SELECT date, content FROM daily_briefings WHERE date = CURRENT_DATE"
        )
        if not row:
            # Fall back to most recent briefing
            row = db.execute_one(
                "SELECT date, content FROM daily_briefings ORDER BY date DESC LIMIT 1"
            )
        if not row:
            return jsonify({"error": "Брифингот сè уште не е подготвен. Обидете се подоцна."}), 200

        return jsonify({
            "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
            "content": row["content"] or ""
        })
    except Exception as e:
        log.error(f"[api/briefing] Error: {e}", exc_info=True)
        return error_response("Failed to fetch briefing")

@api_bp.route("/api/live")
def api_live():
    from utils import event_stream
    return Response(event_stream("updates"), mimetype="text/event-stream")

@api_bp.route("/api/trending")
def api_trending():
    """Return cached trending keywords."""
    try:
        cached = cached_response("trending", ttl=900)
        if cached:
            return jsonify(cached[:30])
        # Fallback: compute now and cache
        from trending import get_trending
        words = get_trending(hours=6, limit=30)
        if words:
            set_cache("trending", words, ttl=900)
        return jsonify(words)
    except Exception as e:
        log.warning(f"[api/trending] {e}")
        return jsonify([])

@api_bp.route("/api/sources/pulse")
def api_sources_pulse():
    """Return top MK sources by article count in last 24h."""
    try:
        rows = db.execute(
            "SELECT source, COUNT(*) as n FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "AND (country = '🇲🇰' OR country IS NULL OR country = '') "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )
        return jsonify([{"source": r["source"], "count": r["n"]} for r in rows])
    except Exception as e:
        log.warning(f"[api/sources/pulse] {e}")
        return jsonify([])

@api_bp.route("/api/chat_cluster", methods=["POST"])
def chat_cluster():
    """AI-powered Q&A about a specific news cluster."""
    try:
        data = request.get_json(silent=True) or {}
        cluster_id = (data.get("cluster_id") or "").strip()
        query = (data.get("query") or "").strip()

        if not cluster_id or not query:
            return error_response("cluster_id and query are required", 400)

        if not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
            return error_response("Invalid cluster_id", 400)

        if len(query) > MAX_Q_LEN:
            return error_response("Query too long", 400)

        # Fetch cluster articles and synthesis for context
        rows = db.execute(
            "SELECT title, description, source FROM articles WHERE cluster_id = %s ORDER BY created_at DESC LIMIT 10",
            (cluster_id,)
        )
        if not rows:
            return error_response("Cluster not found", 404)

        synthesis_row = db.execute_one(
            "SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,)
        )

        # Build context
        context_lines = []
        if synthesis_row and synthesis_row.get("summary"):
            context_lines.append(f"AI Резиме: {synthesis_row['summary']}\n")
        context_lines.append("Статии:")
        for r in rows:
            context_lines.append(f"- [{r['source']}] {r['title']}")
            if r.get('description'):
                context_lines.append(f"  {r['description'][:200]}")

        context = "\n".join(context_lines)
        prompt = f"{context}\n\nПрашање: {query}"

        from prompts import SYNTHESIS_SYSTEM_PROMPT
        system = "Ти си новинарски асистент. Одговори на прашањето на корисникот врз основа само на дадените статии. Биди краток и точен. Одговори на македонски јазик."

        response_text, _ = _call_ai(prompt, system, task_type="chat", max_tokens=500)
        if not response_text:
            return error_response("AI не можеше да одговори", 503)

        return jsonify({"status": "success", "response": response_text})

    except Exception as e:
        log.error(f"[api/chat_cluster] Error: {e}", exc_info=True)
        return error_response("Failed to process query")

@api_bp.route("/proxy")
def proxy_image():
    """Proxy and optimize external images."""
    url = request.args.get("url", "").strip()
    if not url:
        return error_response("Missing url parameter", 400)

    if not re.match(r'^https?://', url):
        return error_response("Invalid URL scheme", 400)

    # Block internal/private ranges and metadata services
    import urllib.parse
    import socket
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    
    # 1. Block known local hostnames
    if hostname in ["localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal"]:
        return error_response("Blocked URL", 403)
        
    # 2. Block cloud metadata IPs (AWS/GCP/Azure/DO)
    if hostname == "169.254.169.254" or hostname == "100.100.100.200":
        return error_response("Blocked URL", 403)

    # 3. Pattern match for common private ranges
    blocked_patterns = [
        r'^127\.', r'^10\.', r'^192\.168\.',
        r'^172\.(1[6-9]|2[0-9]|3[01])\.', r'^::1$', r'^0\.0\.0\.0'
    ]
    for pat in blocked_patterns:
        if re.match(pat, hostname):
            return error_response("Blocked URL", 403)

    cache_key = f"proxy:webp:v1:{url}"
    cached = cached_response(cache_key, ttl=86400) # Longer cache for optimized images
    if cached:
        return Response(
            bytes.fromhex(cached["data"]),
            content_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"}
        )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Presek/5.0 ImageProxy"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if content_type not in _PROXY_ALLOWED_TYPES:
                return error_response("Unsupported content type", 415)

            image_data = resp.read(_PROXY_MAX_BYTES + 1)
            if len(image_data) > _PROXY_MAX_BYTES:
                return error_response("Image too large", 413)

        # Optimize using Pillow
        from io import BytesIO
        from PIL import Image
        
        img = Image.open(BytesIO(image_data))
        
        # Convert to RGB if needed (for WebP/JPEG consistency)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        # Resize if too large (width > 600px)
        max_width = 600
        if img.width > max_width:
            w_percent = (max_width / float(img.width))
            h_size = int((float(img.height) * float(w_percent)))
            img = img.resize((max_width, h_size), Image.Resampling.LANCZOS)
            
        # Save as WebP
        webp_io = BytesIO()
        img.save(webp_io, "WEBP", quality=80, method=6)
        optimized_data = webp_io.getvalue()

        # Cache optimized version
        set_cache(cache_key, {"data": optimized_data.hex(), "content_type": "image/webp"}, ttl=86400)

        return Response(
            optimized_data,
            content_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"}
        )

    except Exception as e:
        log.warning(f"[proxy] Optimization error for {url}: {e}")
        # Fallback: if optimization fails but we have raw data, serve raw (if safe)
        return error_response("Failed to process image", 502)
