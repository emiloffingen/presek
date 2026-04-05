import os
import secrets
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import logging
import datetime
import re
from typing import Optional, List
from collections import defaultdict

from database import db_manager as db
from utils import (
    score_cluster, rank_articles_in_cluster, calculate_reading_time, 
    cached_response, set_cache, is_balanced, assess_cluster_synthesis_freshness,
    annotate_cluster_articles, score_cluster_for_homepage, build_read_next_clusters,
    build_source_reputation_rows, build_editor_analytics_payload,
)
from ai_engine import PROVIDERS, _call_ai_async, clean_json_response
from prompts import SYNTHESIS_SYSTEM_PROMPT
from config import BREAKING_SCORE_THRESHOLD, API_MAX_PAGE, API_MAX_Q_LEN
from local_nlp import (
    answer_cluster_question_locally,
    generate_daily_brief_fallback,
    normalize_tag_name,
    filter_cluster_tags,
    is_valid_focus_entity,
    build_citation_snippet,
    build_structured_answer_sections,
)
from health import _probe_database, _probe_redis
from api_helpers import (
    normalize_perspectives as _parse_perspectives_blob,
    default_related_questions as _default_related_questions,
    related_questions_from_context as _related_questions_from_context,
    text_terms as _text_terms,
    rank_cluster_citations as _rank_cluster_citations,
    normalize_server_delivery_subscription as _normalize_server_delivery_subscription,
)

log = logging.getLogger("presek")

app = FastAPI(title="Presek API 6.0", version="6.0.0")
_start_time = datetime.datetime.now(datetime.timezone.utc)
_public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live").rstrip("/")
_default_cors_origins = [
    _public_site_url,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4321",
    "http://127.0.0.1:4321",
]
_configured_cors_origins = [
    origin.rstrip("/")
    for origin in (o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(","))
    if origin and origin != "*"
]
_cors_origins = _configured_cors_origins or _default_cors_origins

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize_sync_list(values, limit=24):
    cleaned = []
    seen = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _normalize_recent_clusters(items):
    rows = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        cluster_id = str(item.get("cluster_id") or "").strip()
        if not cluster_id or cluster_id in seen:
            continue
        seen.add(cluster_id)
        rows.append({
            "cluster_id": cluster_id,
            "title": str(item.get("title") or "").strip(),
            "category": str(item.get("category") or "").strip(),
            "topic": str(item.get("topic") or "").strip(),
            "primarySource": str(item.get("primarySource") or "").strip(),
            "sources": _normalize_sync_list(item.get("sources") or [], limit=8),
            "tags": _normalize_sync_list(item.get("tags") or [], limit=10),
            "viewedAt": str(item.get("viewedAt") or "").strip(),
        })
        if len(rows) >= 24:
            break
    return rows


def _normalize_delivery_preferences(prefs):
    prefs = prefs or {}
    return {
        "morningBriefing": prefs.get("morningBriefing") is not False,
        "breakingAlerts": prefs.get("breakingAlerts") is not False,
        "browserPermission": str(prefs.get("browserPermission") or "default").strip() or "default",
    }


def _normalize_synced_profile(payload):
    payload = payload or {}
    return {
        "followedTopics": _normalize_sync_list(payload.get("followedTopics") or [], limit=12),
        "followedSources": _normalize_sync_list(payload.get("followedSources") or [], limit=12),
        "recentClusters": _normalize_recent_clusters(payload.get("recentClusters") or []),
        "deliveryPreferences": _normalize_delivery_preferences(payload.get("deliveryPreferences") or {}),
    }


def _merge_synced_profiles(left, right):
    left = _normalize_synced_profile(left)
    right = _normalize_synced_profile(right)

    merged_recent = _normalize_recent_clusters(
        sorted(
            left["recentClusters"] + right["recentClusters"],
            key=lambda item: str(item.get("viewedAt") or ""),
            reverse=True,
        )
    )

    return {
        "followedTopics": _normalize_sync_list(left["followedTopics"] + right["followedTopics"], limit=12),
        "followedSources": _normalize_sync_list(left["followedSources"] + right["followedSources"], limit=12),
        "recentClusters": merged_recent,
        "deliveryPreferences": {
            **left["deliveryPreferences"],
            **right["deliveryPreferences"],
        },
    }


def _default_server_delivery_subscription():
    return _normalize_server_delivery_subscription({})


def _normalize_server_delivery_row(row):
    if not row:
        return _default_server_delivery_subscription()
    return _normalize_server_delivery_subscription({
        "channel": row.get("channel"),
        "target": row.get("target"),
        "morningBriefing": row.get("morning_briefing"),
        "weeklyDigest": row.get("weekly_digest"),
        "breakingTopics": row.get("breaking_topics"),
        "breakingSources": row.get("breaking_sources"),
        "isActive": row.get("is_active"),
    })


def _safe_tracking_redirect_path(path: str) -> str:
    clean = str(path or "").strip()
    if not clean.startswith("/"):
        return "/briefing"
    if clean.startswith("//") or clean.startswith("/api/"):
        return "/briefing"
    return clean

def _is_valid_focus_entity(name: str, entity_type: Optional[str]) -> bool:
    return is_valid_focus_entity(name, entity_type)


def _build_cluster_answer_fallback(question: str, articles, synthesis: str = "", perspectives=None) -> dict:
    articles = [dict(article) if not isinstance(article, dict) else article for article in (articles or [])]
    category = articles[0].get("category") if articles else None
    perspectives = _parse_perspectives_blob(perspectives or [])
    local_answer = None

    try:
        local_answer = answer_cluster_question_locally(
            question,
            articles,
            synthesis=synthesis,
            perspectives=perspectives,
        )
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] local helper failed, using minimal fallback: {e}")

    if not local_answer and articles:
        lead = articles[0]
        lead_title = str(lead.get("title") or "Оваа приказна")
        lead_source = str(lead.get("source") or "Извор").strip()
        local_answer = {
            "answer": f"Најважното во овој момент е: {lead_title}. Водечкиот достапен извор во овој кластер е {lead_source}.",
            "citations": articles[:2],
            "related_questions": _default_related_questions(question, category),
            "confidence": "low",
        }

    sections = {
        "confirmed_points": [],
        "unclear_points": [],
        "source_differences": "",
    }
    try:
        sections = build_structured_answer_sections(
            local_answer["answer"] if local_answer else "",
            articles,
            synthesis=synthesis,
            perspectives=perspectives,
        )
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] section builder failed during fallback: {e}")

    citations = []
    try:
        citations = _rank_cluster_citations(
            question,
            local_answer["answer"] if local_answer else "",
            articles,
            [],
        )
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] citation ranking failed during fallback: {e}")
        citations = [
            {
                "source": article.get("source"),
                "title": article.get("title"),
                "link": article.get("link"),
                "created_at": article.get("created_at"),
                "snippet": build_citation_snippet(article),
            }
            for article in articles[:2]
        ]

    return {
        "status": "success",
        "answer": (local_answer or {}).get("answer", "Во моментов системот не може да даде подетален одговор."),
        "citations": citations,
        "related_questions": (local_answer or {}).get("related_questions") or _related_questions_from_context(
            question,
            category,
            has_perspectives=bool(perspectives),
            has_multiple_sources=len(articles) >= 2,
            has_unclear_points=bool(sections.get("unclear_points")),
        ),
        "confidence": (local_answer or {}).get("confidence", "low"),
        "confirmed_points": sections.get("confirmed_points", [])[:3],
        "unclear_points": sections.get("unclear_points", [])[:2],
        "source_differences": sections.get("source_differences", ""),
        "generated_locally": True,
    }


def _fallback_citations(articles) -> list[dict]:
    return [
        {
            "source": article.get("source"),
            "title": article.get("title"),
            "link": article.get("link"),
            "created_at": article.get("created_at"),
            "snippet": build_citation_snippet(article),
        }
        for article in (articles or [])[:2]
    ]


def _safe_rank_cluster_citations(question: str, answer: str, articles, citation_numbers) -> list[dict]:
    try:
        return _rank_cluster_citations(question, answer, articles, citation_numbers)
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] citation ranking failed: {e}", exc_info=True)
        return _fallback_citations(articles)

@app.get("/api/health")
async def health():
    db_status = _probe_database()
    redis_status = _probe_redis()
    uptime_seconds = int((datetime.datetime.now(datetime.timezone.utc) - _start_time).total_seconds())
    overall = "ok" if (db_status["ok"] and redis_status["ok"]) else "degraded"
    return {
        "status": overall,
        "version": "6.0.0-async",
        "uptime_seconds": uptime_seconds,
        "database": db_status,
        "redis": redis_status,
    }


@app.post("/api/profile/sync/init")
async def init_profile_sync():
    token = secrets.token_urlsafe(18)
    empty_profile = _normalize_synced_profile({})
    db.execute(
        "INSERT INTO synced_reader_profiles (sync_token, profile_data) VALUES (%s, %s::jsonb)",
        (token, json.dumps(empty_profile)),
        fetch=False,
    )
    return {
        "status": "success",
        "token": token,
        "profile": empty_profile,
    }


@app.get("/api/profile/sync")
async def get_profile_sync(token: str = Query(..., min_length=12, max_length=128)):
    row = db.execute_one(
        "SELECT profile_data, updated_at FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Synced profile not found")
    return {
        "status": "success",
        "token": token,
        "profile": _normalize_synced_profile(row.get("profile_data") or {}),
        "updated_at": row.get("updated_at"),
    }


@app.post("/api/profile/sync")
async def save_profile_sync(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing sync token")

    incoming = _normalize_synced_profile(payload.get("profile") or {})
    existing = db.execute_one(
        "SELECT profile_data FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Synced profile not found")

    merged = _merge_synced_profiles(existing.get("profile_data") or {}, incoming)
    db.execute(
        "UPDATE synced_reader_profiles SET profile_data = %s::jsonb, updated_at = NOW() WHERE sync_token = %s",
        (json.dumps(merged), token),
        fetch=False,
    )
    return {
        "status": "success",
        "token": token,
        "profile": merged,
    }


@app.get("/api/profile/delivery")
async def get_profile_delivery(token: str = Query(..., min_length=12, max_length=128)):
    profile = db.execute_one(
        "SELECT 1 FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Synced profile not found")

    row = db.execute_one(
        "SELECT channel, target, morning_briefing, weekly_digest, breaking_topics, breaking_sources, is_active, updated_at "
        "FROM synced_delivery_subscriptions WHERE sync_token = %s",
        (token,),
    )
    return {
        "status": "success",
        "token": token,
        "subscription": _normalize_server_delivery_row(row),
        "updated_at": row.get("updated_at") if row else None,
    }


@app.post("/api/profile/delivery")
async def save_profile_delivery(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing sync token")

    profile = db.execute_one(
        "SELECT 1 FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Synced profile not found")

    subscription = _normalize_server_delivery_subscription(payload.get("subscription") or {})
    db.execute(
        """INSERT INTO synced_delivery_subscriptions
           (sync_token, channel, target, morning_briefing, weekly_digest, breaking_topics, breaking_sources, is_active, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
           ON CONFLICT (sync_token) DO UPDATE SET
             channel = EXCLUDED.channel,
             target = EXCLUDED.target,
             morning_briefing = EXCLUDED.morning_briefing,
             weekly_digest = EXCLUDED.weekly_digest,
             breaking_topics = EXCLUDED.breaking_topics,
             breaking_sources = EXCLUDED.breaking_sources,
             is_active = EXCLUDED.is_active,
             updated_at = NOW()""",
        (
            token,
            subscription["channel"],
            subscription["target"],
            subscription["morningBriefing"],
            subscription["weeklyDigest"],
            subscription["breakingTopics"],
            subscription["breakingSources"],
            subscription["isActive"],
        ),
        fetch=False,
    )
    return {
        "status": "success",
        "token": token,
        "subscription": subscription,
    }


@app.get("/api/delivery/track/{event_type}")
async def track_delivery_event(event_type: str, event_id: int = Query(..., ge=1), redirect: str = Query("/briefing")):
    clean_type = str(event_type or "").strip().lower()
    if clean_type not in {"open", "click"}:
        raise HTTPException(status_code=400, detail="Invalid event type")

    parent = db.execute_one(
        "SELECT sync_token, delivery_kind, channel, target, cluster_id, metadata FROM delivery_tracking_events WHERE id = %s AND event_type = 'send'",
        (event_id,),
    )
    if parent:
        db.execute(
            """INSERT INTO delivery_tracking_events
               (sync_token, parent_event_id, event_type, delivery_kind, channel, target, cluster_id, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
            (
                parent.get("sync_token"),
                event_id,
                clean_type,
                parent.get("delivery_kind"),
                parent.get("channel") or "ntfy",
                parent.get("target") or "",
                parent.get("cluster_id"),
                json.dumps({"redirect": _safe_tracking_redirect_path(redirect)}),
            ),
            fetch=False,
        )

    return RedirectResponse(url=f"{_public_site_url}{_safe_tracking_redirect_path(redirect)}", status_code=302)

@app.get("/api/intelligence/entity/{name}")
async def get_entity_profile(name: str):
    """Returns detailed profile and relationships for an entity."""
    entity = db.execute_one("""
        SELECT name, type, total_mentions, first_seen, last_seen, sentiment_score
        FROM knowledge_entities WHERE name = %s
    """, (name,))
    
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    # Get top relationships
    relationships = db.execute("""
        SELECT 
            CASE WHEN entity_a = %s THEN entity_b ELSE entity_a END as related_entity,
            weight
        FROM knowledge_relationships
        WHERE entity_a = %s OR entity_b = %s
        ORDER BY weight DESC LIMIT 10
    """, (name, name, name))
    
    return {
        "profile": entity,
        "related": relationships
    }

@app.get("/api/intelligence/top-entities")
async def get_top_entities(limit: int = 10):
    """Returns the most mentioned entities."""
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
        if not _is_valid_focus_entity(normalized_name, row.get("type")):
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

@app.get("/api/news")
async def get_news(
    q: Optional[str] = None,
    category: Optional[str] = None,
    topic: Optional[str] = None,
    entity: Optional[str] = None,
    sort: str = "recent",
    page: int = 0,
    page_size: int = 24
):
    try:
        # Fetch clusters with aggregated entity names
        sql = """
            WITH cluster_ents AS (
                SELECT cluster_id, array_agg(entity_name) as entity_names
                FROM cluster_entities
                GROUP BY cluster_id
            )
            SELECT a.*, COALESCE(ce.entity_names, '{}') as entity_names
            FROM (
        """
        params = []
        if q:
            sql += "SELECT * FROM articles WHERE 1=1 AND (title ILIKE %s OR description ILIKE %s) LIMIT 100"
            params = [f'%{q}%', f'%{q}%']
        elif entity:
            sql += """
                SELECT a.* FROM articles a
                JOIN cluster_entities ce ON a.cluster_id = ce.cluster_id
                WHERE ce.entity_name = %s
                ORDER BY a.created_at DESC LIMIT 100
            """
            params = [entity]
        elif topic:
            sql += "SELECT * FROM articles WHERE topic = %s ORDER BY created_at DESC LIMIT 100"
            params = [topic]
        elif category:
            sql += "SELECT * FROM articles WHERE category = %s ORDER BY created_at DESC LIMIT 100"
            params = [category]
        else:
            sql += "SELECT * FROM articles WHERE country = '🇲🇰' ORDER BY created_at DESC LIMIT 200"

        rows = db.execute(sql + ") a LEFT JOIN cluster_ents ce ON a.cluster_id = ce.cluster_id", tuple(params))

        clusters = defaultdict(list)
        for r in rows:
            r['reading_time'] = calculate_reading_time(r.get('description', ''))
            clusters[r['cluster_id']].append(r)

        ranked_clusters = [annotate_cluster_articles(arts) for arts in clusters.values()]
        
        if sort == 'popular':
            ranked_clusters.sort(key=lambda arts: sum(a.get("clicks", 0) or 0 for a in arts), reverse=True)
        else:
            ranked_clusters.sort(key=score_cluster_for_homepage, reverse=True)

        start = page * page_size
        paged_clusters = ranked_clusters[start:start + page_size]

        # Fetch metadata and synthesis status
        cid_list = [c[0]["cluster_id"] for c in paged_clusters]
        if cid_list:
            metadata_rows = db.execute(
                "SELECT cluster_id, representative_image FROM cluster_metadata WHERE cluster_id = ANY(%s)",
                (cid_list,)
            )
            rep_images = {r['cluster_id']: r['representative_image'] for r in metadata_rows}
            
            synthesis_ids = set(db.get_synthesis_ids(cid_list))
        else:
            rep_images = {}
            synthesis_ids = set()

        result = []
        for arts in paged_clusters:
            main = arts[0]
            cid = main["cluster_id"]
            s = score_cluster(arts)
            homepage_score = score_cluster_for_homepage(arts)
            result.append({
                "cluster_id": cid,
                "articles": arts,
                "representative_image": rep_images.get(cid),
                "reading_time": main.get('reading_time', 1),
                "score": round(s, 3),
                "homepage_score": round(homepage_score, 3),
                "is_breaking": s >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts),
                "entities": main.get("entity_names", [])
            })

        return {
            "status": "success",
            "clusters": result,
            "page": page,
            "has_more": len(ranked_clusters) > start + page_size
        }
    except Exception as e:
        log.error(f"FastAPI News Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": str(e)})

@app.get("/api/cluster/{cluster_id}")
async def get_cluster_detail(cluster_id: str):
    """Returns detailed information for a specific cluster."""
    if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")
        
    try:
        # 1. Fetch articles
        rows = db.execute(
            "SELECT * FROM articles WHERE cluster_id = %s ORDER BY created_at DESC", 
            (cluster_id,)
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Cluster not found")
            
        articles = annotate_cluster_articles(rows)
        for a in articles:
            a['reading_time'] = calculate_reading_time(a.get('description', ''))

        # 2. Fetch synthesis and perspectives
        s_row = db.execute_one(
            "SELECT summary, perspectives, created_at FROM cluster_summaries WHERE cluster_id = %s", 
            (cluster_id,)
        )
        synthesis = s_row["summary"] if s_row else None
        perspectives = s_row["perspectives"] if s_row and s_row["perspectives"] else []
        if isinstance(perspectives, str):
            perspectives = json.loads(perspectives)
        freshness = assess_cluster_synthesis_freshness(articles, (s_row or {}).get("created_at"))

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
                WITH cluster_ents AS (
                    SELECT cluster_id, array_agg(entity_name) as entity_names
                    FROM cluster_entities
                    GROUP BY cluster_id
                )
                SELECT a.*, COALESCE(m.tags, '{}') as cluster_tags, COALESCE(ce.entity_names, '{}') as entity_names
                FROM articles a
                LEFT JOIN cluster_metadata m ON a.cluster_id = m.cluster_id
                LEFT JOIN cluster_ents ce ON a.cluster_id = ce.cluster_id
                WHERE a.cluster_id != %s
                  AND a.created_at >= NOW() - INTERVAL '72 hours'
                  AND (
                    m.tags && %s
                    OR EXISTS (
                        SELECT 1 FROM cluster_entities ce2
                        WHERE ce2.cluster_id = a.cluster_id
                          AND ce2.entity_name = ANY(%s)
                    )
                  )
                ORDER BY a.created_at DESC
                LIMIT 120
            """, (cluster_id, tags, list({entity for article in articles for entity in (article.get("entity_names") or [])})))
            related = build_read_next_clusters(cluster_id, articles, tags, related_rows, limit=4)

        return {
            "status": "success",
            "data": {
                "cluster_id": cluster_id,
                "articles": articles,
                "synthesis": synthesis,
                "synthesis_updated_at": freshness["synthesis_updated_at"],
                "synthesis_freshness": {
                    "is_stale": freshness["is_stale"],
                    "new_article_count": freshness["new_article_count"],
                    "reasons": freshness["reasons"],
                },
                "perspectives": perspectives,
                "tags": tags,
                "topics": topics,
                "related": related,
                "total_reading_time": sum(a['reading_time'] for a in articles)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"FastAPI Cluster Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cluster detail")


@app.post("/api/cluster/{cluster_id}/ask")
async def ask_cluster(cluster_id: str, request: Request):
    """Answers a question using only the current cluster's context."""
    try:
        try:
            if not cluster_id or not re.match(r'^[a-f0-9]{6,64}$', cluster_id):
                raise HTTPException(status_code=400, detail="Invalid cluster ID")

            try:
                payload = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")

            question = str((payload or {}).get("question") or "").strip()
            if not question:
                raise HTTPException(status_code=400, detail="Question is required")
            if len(question) > API_MAX_Q_LEN:
                raise HTTPException(status_code=400, detail="Question is too long")

            articles = db.execute(
                """
                SELECT title, description, source, link, created_at, category
                FROM articles
                WHERE cluster_id = %s
                ORDER BY created_at DESC
                LIMIT 8
                """,
                (cluster_id,)
            )
            articles = [dict(article) if not isinstance(article, dict) else article for article in articles]
            if not articles:
                raise HTTPException(status_code=404, detail="Cluster not found")

            summary_row = db.execute_one(
                "SELECT summary, perspectives FROM cluster_summaries WHERE cluster_id = %s",
                (cluster_id,)
            )
            synthesis = (summary_row or {}).get("summary") or ""
            perspectives = _parse_perspectives_blob((summary_row or {}).get("perspectives"))

            try:
                local_answer = answer_cluster_question_locally(question, articles, synthesis=synthesis, perspectives=perspectives)
            except Exception as e:
                log.warning(f"[fastapi cluster_answer] local answer generation failed for {cluster_id}: {e}", exc_info=True)
                return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
            if local_answer:
                try:
                    sections = build_structured_answer_sections(
                        local_answer["answer"],
                        articles,
                        synthesis=synthesis,
                        perspectives=perspectives,
                    )
                except Exception as e:
                    log.warning(f"[fastapi cluster_answer] section building failed for {cluster_id}: {e}", exc_info=True)
                    return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
                return {
                    "status": "success",
                    "answer": local_answer.get("answer", ""),
                    "citations": _safe_rank_cluster_citations(question, local_answer.get("answer", ""), articles, [])[:3],
                    "related_questions": list(local_answer.get("related_questions") or [])[:3],
                    "confidence": local_answer.get("confidence", "medium"),
                    "confirmed_points": sections["confirmed_points"],
                    "unclear_points": sections["unclear_points"],
                    "source_differences": sections["source_differences"],
                    "generated_locally": True,
                }

            article_context = []
            for idx, article in enumerate(articles, start=1):
                article_context.append(
                    f"[{idx}] Извор: {article['source']}\n"
                    f"Наслов: {article['title']}\n"
                    f"Опис: {(article.get('description') or '').strip()}\n"
                )

            perspective_context = "\n".join(
                f"- {item['angle']}: {item['content']}" for item in perspectives[:4]
            )

            prompt = (
                "Контекст за еден новински кластер:\n\n"
                f"Системско резиме:\n{synthesis or 'Нема достапно резиме.'}\n\n"
                f"Перспективи:\n{perspective_context or 'Нема издвоени перспективи.'}\n\n"
                "Извори:\n"
                + "\n".join(article_context)
                + "\n"
                f"Прашање од корисник: {question}\n\n"
                "Одговори само врз основа на контекстот погоре. Ако нешто не е потврдено или недостига, кажи го тоа јасно. "
                "Врати JSON со полиња: "
                "{\"answer\":\"...\",\"confirmed_points\":[\"...\"],\"unclear_points\":[\"...\"],\"source_differences\":\"...\",\"citation_numbers\":[1,2],\"related_questions\":[\"...\",\"...\",\"...\"],\"confidence\":\"high|medium|low\"}. "
                "Во citation_numbers вклучи само броеви од листата на извори што директно го поддржуваат одговорот. "
                "Одговорот мора да биде на македонски."
            )

            system = (
                "Ти си новинарски асистент за Пресек. Не измислувај факти. "
                "Ако контекстот не е доволен, кажи што не е јасно. Биди прецизен и концизен."
            )

            try:
                response_text, _provider = await _call_ai_async(
                    prompt,
                    system,
                    task_type="chat",
                    max_tokens=700,
                    json_mode=True,
                )
            except Exception as e:
                log.warning(f"[fastapi cluster_answer] AI call failed for {cluster_id}: {e}", exc_info=True)
                return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)

            if not response_text:
                return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)

            try:
                parsed = clean_json_response(response_text)
            except Exception as e:
                log.warning(f"[fastapi cluster_answer] AI response cleaning failed for {cluster_id}: {e}", exc_info=True)
                return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
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
                citation_numbers = [1, 2]
                related_questions = []
                confidence = "medium"

            citations = _safe_rank_cluster_citations(question, answer, articles, citation_numbers)
            try:
                sections = build_structured_answer_sections(
                    answer,
                    articles,
                    synthesis=synthesis,
                    perspectives=perspectives,
                )
            except Exception as e:
                log.warning(f"[fastapi cluster_answer] final section building failed for {cluster_id}: {e}", exc_info=True)
                return _build_cluster_answer_fallback(question, articles, synthesis=synthesis, perspectives=perspectives)
            if not confirmed_points:
                confirmed_points = sections["confirmed_points"]
            if not unclear_points:
                unclear_points = sections["unclear_points"]
            if not source_differences:
                source_differences = sections["source_differences"]

            clean_related = []
            for item in related_questions:
                text = str(item).strip()
                if text and text not in clean_related and text != question:
                    clean_related.append(text)

            if not clean_related:
                clean_related = _related_questions_from_context(
                    question,
                    articles[0].get("category"),
                    has_perspectives=bool(perspectives),
                    has_multiple_sources=len(articles) >= 2,
                    has_unclear_points=bool(unclear_points),
                )

            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"

            return {
                "status": "success",
                "answer": answer,
                "citations": citations[:3],
                "related_questions": clean_related[:3],
                "confidence": confidence,
                "confirmed_points": confirmed_points[:3],
                "unclear_points": unclear_points[:2],
                "source_differences": source_differences,
            }
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[fastapi cluster_answer] unexpected error for {cluster_id}: {e}", exc_info=True)
            return _build_cluster_answer_fallback(question, articles if 'articles' in locals() else [], synthesis=synthesis if 'synthesis' in locals() else "", perspectives=perspectives if 'perspectives' in locals() else [])
    except HTTPException:
        raise

@app.get("/api/briefing")
async def get_briefing():
    try:
        row = db.execute_one(
            "SELECT date, content FROM daily_briefings WHERE date = CURRENT_DATE"
        )
        if not row:
            row = db.execute_one(
                "SELECT date, content FROM daily_briefings ORDER BY date DESC LIMIT 1"
            )
        if not row:
            fallback_rows = db.execute(
                "SELECT cluster_id, title, description, source, category, topic, created_at "
                "FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours' ORDER BY created_at DESC LIMIT 10"
            )
            return {
                "date": datetime.date.today().isoformat(),
                "content": generate_daily_brief_fallback(fallback_rows),
                "generated_locally": True,
            }

        return {
            "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]),
            "content": row["content"] or ""
        }
    except Exception as e:
        log.error(f"FastAPI Briefing Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch briefing")

@app.get("/api/archive")
async def get_archive(
    date: str = Query(...),
    source: str = "",
    topic: str = "",
    page: int = 0,
    page_size: int = 50
):
    """Return clustered archive data for a specific date."""
    try:
        datetime.datetime.strptime(date, '%Y-%m-%d')

        offset = page * page_size
        where_clauses = ["created_at::date = %s"]
        params = [date]

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
        synthesis_ids = set(db.get_synthesis_ids(cluster_ids)) if cluster_ids else set()
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
        sources = db.execute_one(
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

        return {
            "clusters": cluster_payload,
            "total": total,
            "sources": sources,
            "date": date,
            "source": source,
            "topic": topic,
            "page": page,
            "page_size": page_size,
            "has_more": offset + page_size < len(ranked_clusters),
            "total_clusters": len(ranked_clusters),
            "top_sources": [dict(r) for r in top_sources],
            "top_topics": [dict(r) for r in top_topics],
        }
    except Exception as e:
        log.error(f"FastAPI Archive Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/stats")
async def get_stats():
    try:
        return {"status": "success", "data": db.get_stats()}
    except Exception as e:
        log.error(f"FastAPI Stats Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.get("/api/stats/full")
async def get_stats_full():
    try:
        cached = cached_response("stats:full", ttl=120)
        if cached:
            return cached

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

        profile_stats_row = db.execute_one(
            "SELECT "
            "COUNT(*) AS synced_profiles, "
            "COUNT(*) FILTER (WHERE updated_at >= NOW() - INTERVAL '7 days') AS active_profiles_7d, "
            "COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'recentClusters', '[]'::jsonb)) > 0) AS profiles_with_recent_reads, "
            "COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) > 0) AS profiles_following_topics, "
            "COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(profile_data->'followedSources', '[]'::jsonb)) > 0) AS profiles_following_sources "
            "FROM synced_reader_profiles"
        ) or {}
        delivery_stats_row = db.execute_one(
            "SELECT "
            "COUNT(*) FILTER (WHERE is_active = TRUE) AS delivery_active, "
            "COUNT(*) FILTER (WHERE COALESCE(target, '') != '') AS delivery_targets, "
            "COUNT(*) FILTER (WHERE morning_briefing = TRUE) AS morning_briefings, "
            "COUNT(*) FILTER (WHERE weekly_digest = TRUE) AS weekly_digests, "
            "COUNT(*) FILTER (WHERE breaking_topics = TRUE) AS breaking_topic_alerts, "
            "COUNT(*) FILTER (WHERE breaking_sources = TRUE) AS breaking_source_alerts "
            "FROM synced_delivery_subscriptions"
        ) or {}
        top_followed_topics = db.execute(
            "SELECT value AS topic, COUNT(*) AS followers "
            "FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedTopics', '[]'::jsonb)) AS value "
            "GROUP BY value ORDER BY followers DESC, topic ASC LIMIT 6"
        )
        top_followed_sources = db.execute(
            "SELECT value AS source, COUNT(*) AS followers "
            "FROM synced_reader_profiles, jsonb_array_elements_text(COALESCE(profile_data->'followedSources', '[]'::jsonb)) AS value "
            "GROUP BY value ORDER BY followers DESC, source ASC LIMIT 6"
        )
        tracking_stats_row = db.execute_one(
            "SELECT "
            "COUNT(*) FILTER (WHERE event_type = 'send') AS sends_7d, "
            "COUNT(*) FILTER (WHERE event_type = 'open') AS opens_7d, "
            "COUNT(*) FILTER (WHERE event_type = 'click') AS clicks_7d "
            "FROM delivery_tracking_events "
            "WHERE created_at >= NOW() - INTERVAL '7 days'"
        ) or {}

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
            "sentiment_index": [],
            "editor_analytics": build_editor_analytics_payload(
                profile_stats_row,
                delivery_stats_row,
                top_followed_topics,
                top_followed_sources,
                tracking_stats_row,
            ),
        }

        set_cache("stats:full", result, ttl=120)
        return result

    except Exception as e:
        log.error(f"FastAPI Stats Full Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@app.get("/api/sources")
async def get_sources():
    """Return source reputation rows."""
    try:
        rows = db.execute(
            "SELECT name, country, category, credibility, is_active, last_fetched, pause_mode, pause_reason, paused_at FROM sources WHERE is_active = TRUE ORDER BY name ASC"
        )
        pulse_rows = db.execute(
            "SELECT source, COUNT(*) as count FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "GROUP BY source"
        )
        speed_rows = db.execute(
            "SELECT source, COUNT(*) AS first_count FROM ("
            "  SELECT DISTINCT ON (cluster_id) cluster_id, source "
            "  FROM articles WHERE created_at >= NOW() - INTERVAL '7 days' "
            "  ORDER BY cluster_id, created_at ASC"
            ") first_articles GROUP BY source ORDER BY first_count DESC"
        )
        history_rows = db.execute(
            "WITH cluster_first AS ("
            "  SELECT DISTINCT ON (cluster_id) cluster_id, source, created_at "
            "  FROM articles "
            "  WHERE created_at >= NOW() - INTERVAL '30 days' "
            "  ORDER BY cluster_id, created_at ASC"
            "), cluster_counts AS ("
            "  SELECT cluster_id, COUNT(DISTINCT source) AS source_count "
            "  FROM articles "
            "  WHERE created_at >= NOW() - INTERVAL '30 days' "
            "  GROUP BY cluster_id"
            "), source_weeks AS ("
            "  SELECT source, "
            "    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS recent_7d_volume, "
            "    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '14 days' AND created_at < NOW() - INTERVAL '7 days') AS previous_7d_volume "
            "  FROM articles "
            "  WHERE created_at >= NOW() - INTERVAL '14 days' "
            "  GROUP BY source"
            ") "
            "SELECT cf.source, "
            "  COUNT(*) AS lead_count_30d, "
            "  COUNT(*) FILTER (WHERE cc.source_count >= 2) AS corroborated_lead_count_30d, "
            "  COUNT(*) FILTER (WHERE cc.source_count = 1) AS solo_lead_count_30d, "
            "  COALESCE(sw.recent_7d_volume, 0) AS recent_7d_volume, "
            "  COALESCE(sw.previous_7d_volume, 0) AS previous_7d_volume "
            "FROM cluster_first cf "
            "LEFT JOIN cluster_counts cc ON cc.cluster_id = cf.cluster_id "
            "LEFT JOIN source_weeks sw ON sw.source = cf.source "
            "GROUP BY cf.source, sw.recent_7d_volume, sw.previous_7d_volume"
        )
        return build_source_reputation_rows(rows, pulse_rows, speed_rows, history_rows)
    except Exception as e:
        log.warning(f"FastAPI Sources Error: {e}")
        return []

@app.get("/api/sources/pulse")
async def get_sources_pulse():
    """Return top MK sources by article count in last 24h."""
    try:
        rows = db.execute(
            "SELECT source, COUNT(*) as n FROM articles "
            "WHERE created_at >= NOW() - INTERVAL '24 hours' "
            "AND (country = '🇲🇰' OR country IS NULL OR country = '') "
            "GROUP BY source ORDER BY n DESC LIMIT 10"
        )
        return [{"source": r["source"], "count": r["n"]} for r in rows]
    except Exception as e:
        log.warning(f"FastAPI Pulse Error: {e}")
        return []

@app.get("/api/chat/stream")
async def chat_stream(cluster_id: str, query: str):
    """Streams AI response for a specific cluster."""
    
    # 1. Get cluster context
    articles = db.execute("SELECT title, description, source FROM articles WHERE cluster_id = %s LIMIT 10", (cluster_id,))
    if not articles:
        raise HTTPException(status_code=404, detail="Cluster not found")
    
    context = "\n".join([f"- [{a['source']}]: {a['title']}" for a in articles])

    async def generate():
        try:
            full_prompt = f"Context:\n{context}\n\nUser Question: {query}"
            generator = await _call_ai_async(full_prompt, SYNTHESIS_SYSTEM_PROMPT, task_type="chat", stream=True)
            if generator:
                async for chunk in generator:
                    if chunk:
                        yield f"data: {json.dumps({'token': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/api/trending")
async def get_trending():
    from trending import get_trending
    words = get_trending(limit=20)
    return words
