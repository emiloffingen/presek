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
from ai_engine import sync_call_ai as _call_ai, clean_json_response
from utils import score_cluster, rank_articles_in_cluster, cached_response, set_cache, calculate_reading_time, is_balanced
from config import BREAKING_SCORE_THRESHOLD, API_MAX_PAGE, API_MAX_Q_LEN
from config import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY
from embeddings import generate_query_embedding
from local_nlp import (
    answer_cluster_question_locally,
    generate_daily_brief_fallback,
    normalize_tag_name,
    filter_cluster_tags,
    is_valid_focus_entity,
    build_citation_snippet,
    build_structured_answer_sections,
)
from health import get_source_statuses

api_bp = Blueprint('api', __name__)
log = logging.getLogger("presek")

# Allowed image content types for proxy
_PROXY_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"}
_PROXY_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _source_admin_authorized():
    token = (request.headers.get("X-Admin-Token") or "").strip()
    expected = (os.environ.get("PRESEK_ADMIN_TOKEN") or os.environ.get("SECRET_KEY") or "").strip()
    remote_addr = (request.remote_addr or "").strip()
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()

    if expected and token and token == expected:
        return True
    if remote_addr in {"127.0.0.1", "::1"} and not forwarded_for:
        return True
    return False


def normalize_perspectives(raw_perspectives):
    if not isinstance(raw_perspectives, list):
        return []

    normalized = []
    for item in raw_perspectives:
        if isinstance(item, dict):
            angle = (
                item.get("angle")
                or item.get("label")
                or item.get("title")
                or item.get("name")
                or ""
            )
            content = (
                item.get("content")
                or item.get("text")
                or item.get("description")
                or ""
            )
        elif isinstance(item, str):
            angle = ""
            content = item
        else:
            continue

        angle = str(angle).strip()
        content = str(content).strip()
        if not angle and not content:
            continue

        normalized.append({
            "angle": angle or "Перспектива",
            "content": content,
        })

    return normalized


def _default_related_questions(question, category=None):
    fallback = [
        "Што е главниот развој во оваа приказна?",
        "Како се разликуваат изворите во известувањето?",
        "Што сè уште не е потврдено?",
    ]
    if category:
        fallback[0] = f"Кој е најважниот развој во темата {str(category).lower()}?"
    return [q for q in fallback if q.strip() and q.strip() != question.strip()][:3]


def _text_terms(text):
    terms = re.findall(r"[A-Za-zА-Яа-яЀ-ӿ0-9]{3,}", (text or "").lower())
    return {
        term for term in terms
        if term not in {"вести", "вест", "извор", "извори", "кластер"}
    }


def _rank_cluster_citations(question, answer, rows, preferred_numbers):
    question_terms = _text_terms(question)
    answer_terms = _text_terms(answer)
    combined_terms = question_terms | answer_terms

    preferred_order = []
    for raw in preferred_numbers or []:
        try:
            idx = int(raw)
        except Exception:
            continue
        if idx not in preferred_order:
            preferred_order.append(idx)

    ranked = []
    for idx, row in enumerate(rows, start=1):
        article_text = " ".join([
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            str(row.get("source") or ""),
        ])
        article_terms = _text_terms(article_text)
        overlap = len(combined_terms & article_terms)
        preferred_bonus = 5 if idx in preferred_order else 0
        title_bonus = 1 if question_terms & _text_terms(str(row.get("title") or "")) else 0
        ranked.append((
            preferred_bonus + overlap + title_bonus,
            -idx,
            {
                "source": row.get("source"),
                "title": row.get("title"),
                "link": row.get("link"),
                "created_at": row.get("created_at"),
                "snippet": build_citation_snippet(row),
            },
        ))

    ranked.sort(reverse=True)
    top = [item[2] for item in ranked if item[0] > 0]
    if top:
        return top[:3]
    return [
        {
            "source": row.get("source"),
            "title": row.get("title"),
            "link": row.get("link"),
            "created_at": row.get("created_at"),
            "snippet": build_citation_snippet(row),
        }
        for row in rows[:2]
    ]


def _get_top_entities_payload(limit=10):
    fetch_limit = max(limit * 4, 24)
    rows = db.execute("""
        SELECT name, type, total_mentions
        FROM knowledge_entities
        ORDER BY total_mentions DESC LIMIT %s
    """, (fetch_limit,))

    filtered = []
    seen = set()
    for row in rows:
        normalized_name = normalize_tag_name(row["name"])
        if not is_valid_focus_entity(normalized_name, row.get("type")):
            continue
        dedupe_key = normalized_name.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        filtered.append({
            "name": normalized_name,
            "type": row.get("type"),
            "total_mentions": row.get("total_mentions"),
        })
        if len(filtered) >= limit:
            break
    return filtered


def _build_cluster_answer(cluster_id, query):
    rows = db.execute(
        """
        SELECT title, description, source, link, created_at, category
        FROM articles
        WHERE cluster_id = %s
        ORDER BY created_at DESC
        LIMIT 8
        """,
        (cluster_id,)
    )
    if not rows:
        return None, ("Cluster not found", 404)

    synthesis_row = db.execute_one(
        "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s",
        (cluster_id,)
    )
    synthesis = synthesis_row["summary"] if synthesis_row and synthesis_row.get("summary") else ""
    perspectives = normalize_perspectives(
        synthesis_row["perspectives"] if synthesis_row and synthesis_row.get("perspectives") else []
    )

    local_answer = answer_cluster_question_locally(query, rows, synthesis=synthesis, perspectives=perspectives)
    if local_answer:
        sections = build_structured_answer_sections(
            local_answer["answer"],
            rows,
            synthesis=synthesis,
            perspectives=perspectives,
        )
        payload = {
            **local_answer,
            "citations": _rank_cluster_citations(query, local_answer["answer"], rows, []),
            "confirmed_points": sections["confirmed_points"],
            "unclear_points": sections["unclear_points"],
            "source_differences": sections["source_differences"],
            "generated_locally": True,
        }
        return payload, None

    context_lines = []
    if synthesis:
        context_lines.append(f"Системско резиме:\n{synthesis}\n")
    if perspectives:
        context_lines.append("Перспективи:")
        for item in perspectives[:4]:
            context_lines.append(f"- {item['angle']}: {item['content']}")
        context_lines.append("")
    context_lines.append("Извори:")
    for idx, row in enumerate(rows, start=1):
        context_lines.append(f"[{idx}] Извор: {row['source']}")
        context_lines.append(f"Наслов: {row['title']}")
        if row.get("description"):
            context_lines.append(f"Опис: {row['description'][:280]}")
        context_lines.append("")

    prompt = (
        "\n".join(context_lines)
        + f"\nПрашање од корисник: {query}\n\n"
        + "Одговори само врз основа на дадениот контекст. Ако нешто недостига или не е потврдено, кажи го тоа јасно. "
        + "Врати JSON со полиња "
        + "{\"answer\":\"...\",\"confirmed_points\":[\"...\"],\"unclear_points\":[\"...\"],\"source_differences\":\"...\",\"citation_numbers\":[1,2],\"related_questions\":[\"...\",\"...\",\"...\"],\"confidence\":\"high|medium|low\"}. "
        + "Одговорот мора да биде на македонски."
    )
    system = (
        "Ти си новинарски асистент за Пресек. Не измислувај факти. "
        "Биди прецизен, краток и јасно посочи кога нешто не е потврдено."
    )

    response_text, _ = _call_ai(prompt, system, task_type="chat", max_tokens=700, json_mode=True)
    if not response_text:
        return None, ("Системот не можеше да одговори", 503)

    parsed = clean_json_response(response_text)
    if isinstance(parsed, dict):
        answer = str(parsed.get("answer") or "").strip()
        confirmed_points = [str(item).strip() for item in parsed.get("confirmed_points") or [] if str(item).strip()]
        unclear_points = [str(item).strip() for item in parsed.get("unclear_points") or [] if str(item).strip()]
        source_differences = str(parsed.get("source_differences") or "").strip()
        citation_numbers = parsed.get("citation_numbers") or []
        related_questions = parsed.get("related_questions") or []
        confidence = str(parsed.get("confidence") or "medium").strip().lower()
    else:
        answer = str(parsed).strip()
        confirmed_points = []
        unclear_points = []
        source_differences = ""
        citation_numbers = []
        related_questions = []
        confidence = "medium"

    sections = build_structured_answer_sections(
        answer,
        rows,
        synthesis=synthesis,
        perspectives=perspectives,
    )
    if not confirmed_points:
        confirmed_points = sections["confirmed_points"]
    if not unclear_points:
        unclear_points = sections["unclear_points"]
    if not source_differences:
        source_differences = sections["source_differences"]

    payload = {
        "answer": answer,
        "citations": _rank_cluster_citations(query, answer, rows, citation_numbers),
        "related_questions": [str(item).strip() for item in related_questions if str(item).strip()][:3],
        "confidence": confidence if confidence in {"high", "medium", "low"} else "medium",
        "confirmed_points": confirmed_points[:3],
        "unclear_points": unclear_points[:2],
        "source_differences": source_differences,
    }
    if not payload["related_questions"]:
        payload["related_questions"] = _default_related_questions(query, rows[0].get("category"))

    return payload, None

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
        # Validate and constrain pagination parameters
        try:
            page = int(request.args.get("page", 0))
            page_size = int(request.args.get("page_size", 50))
        except ValueError:
            return error_response("Invalid page or page_size: must be integers", 400)
        
        page = min(max(0, page), API_MAX_PAGE)
        page_size = min(200, max(1, page_size))

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
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            log.debug(f"Failed to decode country emoji: {e}")

        sub       = request.args.get("sub", "").strip()
        ids       = request.args.get("ids", "").strip()
        sort_by   = request.args.get("sort", "recent")
        topic     = request.args.get("topic", "").strip()
        sentiment = request.args.get("sentiment", "").strip()
        q         = request.args.get("q", "").strip()[:API_MAX_Q_LEN]
        follow_sources = request.args.get("follow_sources", "").strip()
        follow_topics  = request.args.get("follow_topics", "").strip()

        from categories import ALLOWED_CATEGORIES, THEMATIC_TOPICS
        req_category = None
        req_topic = topic
        
        # If the user selected a geographic category
        if topic in ALLOWED_CATEGORIES:
            req_category = topic
            req_topic = ""
        # If the user selected a thematic topic (Sport, Tech, Economy)
        # we treat it as a global filter by clearing the default country if not explicitly set
        elif topic in THEMATIC_TOPICS:
            # If country was default 🇲🇰 and user clicked "Sport", make it global
            if "country" not in request.args:
                country = "" 

        cache_key = f"v4:news:{country}:{sub}:{ids}:{sort_by}:{topic}:{sentiment}:{follow_sources}:{follow_topics}:{q}:{page}:{page_size}:{req_category}"
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
            rows = db.get_articles_by_country(country, sub=sub, topic=req_topic, sentiment=sentiment, category=req_category)

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
        
        # Fetch representative images
        metadata_rows = db.execute(
            "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
            ([c[0]["cluster_id"] for c in paged_clusters],)
        )
        rep_images = {r['cluster_id']: r['representative_image'] for r in metadata_rows}

        result = []
        for arts in paged_clusters:
            s = score_cluster(arts)
            cid = arts[0]["cluster_id"]
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": arts[0].get('reading_time', 1),
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

        set_cache(cache_key, final_json, ttl=30)
        return jsonify(final_json)

    except Exception as e:
        log.error(f"[api/news] Error: {e}", exc_info=True)
        return error_response("Failed to fetch news")


@api_bp.route("/api/intelligence/entity/<name>")
def api_entity_profile(name):
    entity = db.execute_one("""
        SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score
        FROM knowledge_entities WHERE name = %s
    """, (name,))
    if not entity:
        return error_response("Entity not found", 404)

    relationships = db.execute("""
        SELECT
            CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity,
            weight
        FROM knowledge_relationships
        WHERE entity_a = %s OR entity_b = %s
        ORDER BY weight DESC LIMIT 10
    """, (name, name, name))

    return jsonify({
        "profile": entity,
        "related": relationships,
    })


@api_bp.route("/api/intelligence/top-entities")
def api_top_entities():
    try:
        limit = max(1, min(30, int(request.args.get("limit", 10))))
    except ValueError:
        return error_response("Invalid limit", 400)
    return jsonify(_get_top_entities_payload(limit))

@api_bp.route("/api/cluster/<cluster_id>")
def api_cluster_detail(cluster_id):
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        return error_response("Invalid cluster ID", 400)
        
    try:
        cache_key = f"cluster:detail:{cluster_id}"
        cached = cached_response(cache_key, ttl=45)
        if cached:
            return success_response(cached)

        # 1. Fetch articles
        rows = db.execute(
            "SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", 
            (cluster_id,)
        )
        if not rows:
            return error_response("Cluster not found", 404)
            
        articles = rank_articles_in_cluster(rows)
        for a in articles:
            a['reading_time'] = calculate_reading_time(a.get('description', ''))

        # 2. Fetch synthesis and perspectives
        s_row = db.execute_one(
            "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s", 
            (cluster_id,)
        )
        synthesis = s_row["summary"] if s_row else None
        perspectives = normalize_perspectives(s_row["perspectives"] if s_row and s_row["perspectives"] else [])

        # 3. Fetch metadata (tags, etc)
        m_row = db.execute_one(
            "SELECT tags, topics FROM cluster_metadata WHERE cluster_id = %s", 
            (cluster_id,)
        )
        tags = filter_cluster_tags(m_row["tags"] if m_row else [])
        topics = m_row["topics"] if m_row else []

        # 4. Related clusters
        related = []
        if tags:
            related_rows = db.execute("""
                SELECT 
                    m.cluster_id, 
                    (SELECT title FROM articles WHERE cluster_id = m.cluster_id ORDER BY created_at DESC LIMIT 1) as title,
                    (SELECT image_url FROM articles WHERE cluster_id = m.cluster_id AND image_url IS NOT NULL ORDER BY created_at DESC LIMIT 1) as image_url
                FROM cluster_metadata m
                WHERE m.cluster_id != %s
                  AND m.updated_at >= NOW() - INTERVAL '48 hours'
                  AND m.tags && %s
                ORDER BY m.updated_at DESC
                LIMIT 4
            """, (cluster_id, tags))
            related = related_rows

        payload = {
            "cluster_id": cluster_id,
            "articles": articles,
            "synthesis": synthesis,
            "perspectives": perspectives,
            "tags": tags,
            "topics": topics,
            "related": related,
            "total_reading_time": sum(a['reading_time'] for a in articles)
        }
        set_cache(cache_key, payload, ttl=45)
        return success_response(payload)
    except Exception as e:
        log.error(f"[api/cluster] {e}", exc_info=True)
        return error_response("Failed to fetch cluster detail")

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
        cached = cached_response("stats:full", ttl=60)
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

        set_cache("stats:full", result, ttl=60)
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
            fallback_rows = db.execute(
                "SELECT cluster_id, title, description, source, category, topic, created_at "
                "FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 10"
            )
            return jsonify({
                "date": datetime.date.today().isoformat(),
                "content": generate_daily_brief_fallback(fallback_rows),
                "generated_locally": True,
            })

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

_WMO_ICON = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌦️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "❄️", 73: "❄️", 75: "❄️", 77: "❄️",
    80: "🌦️", 81: "🌦️", 82: "🌦️",
    85: "❄️", 86: "❄️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}

@api_bp.route("/api/weather")
def api_weather():
    """Live weather and AQI for Skopje via Open-Meteo (no API key required)."""
    cached = cached_response("weather:skopje", ttl=900)
    if cached:
        return jsonify(cached)
    try:
        weather_req = urllib.request.Request(
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=41.9981&longitude=21.4254"
            "&current=temperature_2m,weather_code&timezone=Europe%2FSkopje",
            headers={"User-Agent": "Presek/5.0"}
        )
        aqi_req = urllib.request.Request(
            "https://air-quality-api.open-meteo.com/v1/air-quality"
            "?latitude=41.9981&longitude=21.4254"
            "&current=us_aqi&timezone=Europe%2FSkopje",
            headers={"User-Agent": "Presek/5.0"}
        )
        with urllib.request.urlopen(weather_req, timeout=5) as r:
            w = json.loads(r.read())
        with urllib.request.urlopen(aqi_req, timeout=5) as r:
            a = json.loads(r.read())

        temp = round(w["current"]["temperature_2m"])
        code = w["current"]["weather_code"]
        icon = _WMO_ICON.get(code, "🌡️")
        aqi  = a["current"]["us_aqi"]

        result = {"temp": temp, "icon": icon, "aqi": aqi}
        set_cache("weather:skopje", result, ttl=900)
        return jsonify(result)
    except Exception as e:
        log.warning(f"[api/weather] {e}")
        return jsonify({"temp": None, "icon": "🌡️", "aqi": None})


@api_bp.route("/api/trending")
def api_trending():
    """Return cached trending keywords."""
    try:
        cached = cached_response("trending", ttl=300)
        if cached:
            return jsonify(cached[:30])
        # Fallback: compute now and cache
        from trending import get_trending
        words = get_trending(hours=6, limit=30)
        if words:
            set_cache("trending", words, ttl=300)
        return jsonify(words)
    except Exception as e:
        log.warning(f"[api/trending] {e}")
        return jsonify([])


@api_bp.route("/api/archive")
def api_archive():
    try:
        date_str = (request.args.get("date") or "").strip()
        source = (request.args.get("source") or "").strip()
        topic = (request.args.get("topic") or "").strip()
        page = max(0, int(request.args.get("page", 0)))
        page_size = min(100, max(1, int(request.args.get("page_size", 50))))
    except ValueError:
        return error_response("Invalid archive parameters", 400)

    if not date_str:
        date_str = datetime.date.today().isoformat()

    try:
        target_date = datetime.date.fromisoformat(date_str)
    except ValueError:
        return error_response("Invalid date format", 400)

    offset = page * page_size

    try:
        where_clauses = ["created_at::date = %s"]
        params = [target_date.isoformat()]

        if source:
            where_clauses.append("source = %s")
            params.append(source)

        if topic:
            where_clauses.append("topic = %s")
            params.append(topic)

        where_sql = " AND ".join(where_clauses)

        rows = db.execute(
            "SELECT * FROM articles "
            f"WHERE {where_sql} "
            "ORDER BY created_at DESC LIMIT 1500",
            tuple(params)
        )
        clusters = defaultdict(list)
        for row in rows:
            row["reading_time"] = calculate_reading_time(row.get("description", ""))
            clusters[row["cluster_id"]].append(row)

        ranked_clusters = [rank_articles_in_cluster(arts) for arts in clusters.values()]
        ranked_clusters.sort(key=score_cluster, reverse=True)

        paged_clusters = ranked_clusters[offset: offset + page_size]
        cluster_ids = [cluster[0]["cluster_id"] for cluster in paged_clusters]
        synthesis_ids = db.get_synthesis_ids(cluster_ids) if cluster_ids else []
        metadata_rows = db.execute(
            "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
            (cluster_ids or [""],)
        ) if cluster_ids else []
        rep_images = {r["cluster_id"]: r["representative_image"] for r in metadata_rows}

        cluster_payload = []
        for arts in paged_clusters:
            cid = arts[0]["cluster_id"]
            s = score_cluster(arts)
            cluster_payload.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": arts[0].get("reading_time", 1),
                "score": round(s, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts),
            })

        total = db.execute_one(
            f"SELECT COUNT(*) FROM articles WHERE {where_sql}",
            tuple(params)
        )["count"]
        sources_count = db.execute_one(
            f"SELECT COUNT(DISTINCT source) FROM articles WHERE {where_sql}",
            tuple(params)
        )["count"]
        top_sources = db.execute(
            f"SELECT source, COUNT(*) AS n FROM articles WHERE {where_sql} "
            "GROUP BY source ORDER BY n DESC LIMIT 8",
            tuple(params)
        )
        top_topics = db.execute(
            f"SELECT topic, COUNT(*) AS n FROM articles WHERE {where_sql} "
            "GROUP BY topic ORDER BY n DESC LIMIT 8",
            tuple(params)
        )

        return jsonify({
            "clusters": cluster_payload,
            "total": total,
            "sources": sources_count,
            "date": target_date.isoformat(),
            "source": source,
            "topic": topic,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < len(ranked_clusters),
            "total_clusters": len(ranked_clusters),
            "top_sources": [dict(r) for r in top_sources],
            "top_topics": [dict(r) for r in top_topics],
        })
    except Exception as e:
        log.error(f"[api/archive] {e}", exc_info=True)
        return error_response("Failed to fetch archive")

@api_bp.route("/api/sources")
def api_sources():
    """Return all active sources with metadata."""
    try:
        include_inactive = (request.args.get("include_inactive") or "").strip() in {"1", "true", "yes"}
        where_sql = "" if include_inactive else "WHERE is_active = TRUE"
        rows = db.execute(
            f"SELECT name, country, category, credibility, is_active, last_fetched FROM sources {where_sql} ORDER BY name ASC"
        )
        source_statuses = get_source_statuses()
        payload = []
        for row in rows:
            item = dict(row)
            item["source_status"] = source_statuses.get(item["name"])
            payload.append(item)
        return jsonify(payload)
    except Exception as e:
        log.error(f"[api/sources] {e}")
        return error_response("Failed to fetch sources")


@api_bp.route("/api/sources/<name>/control", methods=["POST"])
def api_source_control(name):
    if not _source_admin_authorized():
        return error_response("Unauthorized", 403)
    if not request.is_json:
        return error_response("Content-Type must be application/json", 415)

    source_name = (name or "").strip()
    if not source_name:
        return error_response("Source name is required", 400)

    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").strip().lower()
    valid_actions = {"pause", "resume", "downrank", "uprank", "reset"}
    if action not in valid_actions:
        return error_response("Invalid action", 400)

    source = db.execute_one(
        "SELECT name, country, category, credibility, is_active, last_fetched FROM sources WHERE name = %s",
        (source_name,),
    )
    if not source:
        return error_response("Source not found", 404)

    current_cred = float(source.get("credibility") or DEFAULT_CREDIBILITY)
    if action == "pause":
        db.execute("UPDATE sources SET is_active = FALSE WHERE name = %s", (source_name,), fetch=False)
    elif action == "resume":
        db.execute("UPDATE sources SET is_active = TRUE WHERE name = %s", (source_name,), fetch=False)
    elif action == "downrank":
        db.execute(
            "UPDATE sources SET credibility = %s WHERE name = %s",
            (max(0.4, round(current_cred - 0.2, 2)), source_name),
            fetch=False,
        )
    elif action == "uprank":
        db.execute(
            "UPDATE sources SET credibility = %s WHERE name = %s",
            (min(3.0, round(current_cred + 0.2, 2)), source_name),
            fetch=False,
        )
    elif action == "reset":
        db.execute(
            "UPDATE sources SET credibility = %s WHERE name = %s",
            (SOURCE_CREDIBILITY.get(source_name, DEFAULT_CREDIBILITY), source_name),
            fetch=False,
        )

    updated = db.execute_one(
        "SELECT name, country, category, credibility, is_active, last_fetched FROM sources WHERE name = %s",
        (source_name,),
    )
    if updated:
        updated = dict(updated)
        updated["source_status"] = get_source_statuses().get(source_name)
    return jsonify({"status": "success", "source": updated})

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
        # Require JSON content-type to prevent cross-site form-based CSRF
        if not request.is_json:
            return error_response("Content-Type must be application/json", 415)

        data = request.get_json(silent=True) or {}
        cluster_id = (data.get("cluster_id") or "").strip()
        query = (data.get("query") or "").strip()

        if not cluster_id or not query:
            return error_response("cluster_id and query are required", 400)

        if not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
            return error_response("Invalid cluster_id", 400)

        if len(query) > API_MAX_Q_LEN:
            return error_response("Query too long", 400)

        payload, err = _build_cluster_answer(cluster_id, query)
        if err:
            return error_response(err[0], err[1])

        return jsonify({
            "status": "success",
            "response": payload["answer"],
            "answer": payload["answer"],
            "citations": payload["citations"],
            "related_questions": payload["related_questions"],
            "confidence": payload["confidence"],
            "confirmed_points": payload.get("confirmed_points", []),
            "unclear_points": payload.get("unclear_points", []),
            "source_differences": payload.get("source_differences", ""),
        })

    except Exception as e:
        log.error(f"[api/chat_cluster] Error: {e}", exc_info=True)
        return error_response("Failed to process query")


@api_bp.route("/api/cluster/<cluster_id>/ask", methods=["POST"])
def ask_cluster(cluster_id):
    if not request.is_json:
        return error_response("Content-Type must be application/json", 415)

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return error_response("Question is required", 400)
    if len(question) > API_MAX_Q_LEN:
        return error_response("Question too long", 400)
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        return error_response("Invalid cluster ID", 400)

    try:
        payload, err = _build_cluster_answer(cluster_id, question)
        if err:
            return error_response(err[0], err[1])

        return jsonify({
            "status": "success",
            "answer": payload["answer"],
            "citations": payload["citations"],
            "related_questions": payload["related_questions"],
            "confidence": payload["confidence"],
            "confirmed_points": payload.get("confirmed_points", []),
            "unclear_points": payload.get("unclear_points", []),
            "source_differences": payload.get("source_differences", ""),
        })
    except Exception as e:
        log.error(f"[api/cluster/<cluster_id>/ask] Error: {e}", exc_info=True)
        return error_response("Failed to process query")

@api_bp.route("/proxy")
def proxy_image():
    """Proxy and optimize external images with SSRF protection."""
    url = request.args.get("url", "").strip()
    if not url:
        return error_response("Missing url parameter", 400)

    # Allow serving local static files directly
    if url.startswith("/static/"):
        # Security check: Ensure we stay within the static folder
        if ".." in url:
            return error_response("Blocked URL", 403)
        
        # Determine mimetype
        mimetype = "image/jpeg"
        if url.endswith(".svg"): mimetype = "image/svg+xml"
        elif url.endswith(".png"): mimetype = "image/png"
        elif url.endswith(".webp"): mimetype = "image/webp"
        
        try:
            full_path = os.path.join(os.getcwd(), url.lstrip("/"))
            if os.path.exists(full_path):
                with open(full_path, "rb") as f:
                    return Response(
                        f.read(),
                        content_type=mimetype,
                        headers={"Cache-Control": "public, max-age=86400"}
                    )
            return error_response("Local file not found", 404)
        except Exception as e:
            return error_response(f"Failed to serve local file: {e}", 500)

    if not re.match(r'^https?://', url):
        return error_response("Invalid URL scheme", 400)

    import urllib.parse
    import socket
    import ipaddress
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.ssl_ import create_urllib3_context

    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return error_response("Blocked URL", 403)

    if hostname in {"localhost", "metadata.google.internal", "metadata.internal"}:
        return error_response("Blocked URL", 403)

    def _is_private_ip(addr: str) -> bool:
        try:
            ip = ipaddress.ip_address(addr)
            return (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_multicast or ip.is_reserved or ip.is_unspecified)
        except ValueError:
            return True # Treat invalid IPs as private/unsafe

    # Resolve and pin IP
    try:
        resolved_infos = socket.getaddrinfo(hostname, None)
        safe_ip = None
        for info in resolved_infos:
            ip = info[4][0]
            if not _is_private_ip(ip):
                safe_ip = ip
                break
        
        if not safe_ip:
            return error_response("Blocked URL (Private/Reserved IP)", 403)
            
    except socket.gaierror:
        return error_response("Could not resolve hostname", 404)

    try:
        width_arg = request.args.get("w")
        target_width = int(width_arg) if width_arg and width_arg.isdigit() else 600
        # Sanitize width: min 20 (LQIP), max 1200
        target_width = max(20, min(1200, target_width))
    except ValueError:
        target_width = 600

    cache_key = f"proxy:webp:v2:{target_width}:{url}"
    cached = cached_response(cache_key, ttl=86400)
    if cached:
        return Response(
            bytes.fromhex(cached["data"]),
            content_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"}
        )

    try:
        # Simple fetch with basic headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Use session for better SSL handling
        s = requests.Session()
        response = s.get(
            url, 
            headers=headers, 
            timeout=10, 
            stream=True, 
            verify=True
        )
        
        if response.status_code != 200:
            return error_response("Failed to fetch image", response.status_code)

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in _PROXY_ALLOWED_TYPES:
            return error_response("Unsupported content type", 415)

        image_data = b""
        for chunk in response.iter_content(chunk_size=8192):
            image_data += chunk
            if len(image_data) > _PROXY_MAX_BYTES:
                return error_response("Image too large", 413)

        # Optimize using Pillow
        from io import BytesIO
        from PIL import Image
        
        img = Image.open(BytesIO(image_data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        if img.width > target_width:
            w_percent = (target_width / float(img.width))
            h_size = int((float(img.height) * float(w_percent)))
            img = img.resize((target_width, h_size), Image.Resampling.LANCZOS)
            
        webp_io = BytesIO()
        # For LQIP (very small width), use lower quality to save more space
        quality = 20 if target_width <= 50 else 80
        img.save(webp_io, "WEBP", quality=quality, method=6)
        optimized_data = webp_io.getvalue()

        set_cache(cache_key, {"data": optimized_data.hex(), "content_type": "image/webp"}, ttl=86400)

        return Response(
            optimized_data,
            content_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"}
        )

    except Exception as e:
        log.warning(f"[proxy] Optimization error for {url}: {e}")
        return error_response("Failed to process image", 502)
