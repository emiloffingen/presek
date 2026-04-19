import json
import secrets
import logging
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException

from database import db_manager as db
from utils import (
    delete_cache, score_cluster, is_balanced, 
    score_cluster_for_homepage, annotate_cluster_articles
)
from config import BREAKING_SCORE_THRESHOLD
from api_helpers import normalize_server_delivery_subscription as _normalize_server_delivery_subscription
from .common import _normalize_sync_list, _extract_sync_token, _normalize_suggestion_surface, _normalize_suggestion_kind, _normalize_suggestion_event_type
from .security import validate_string_param

log = logging.getLogger("presek")
router = APIRouter()

def _normalize_delivery_preferences(prefs):
    prefs = prefs or {}
    return {
        "morningBriefing": prefs.get("morningBriefing") is not False,
        "breakingAlerts": prefs.get("breakingAlerts") is not False,
        "browserPermission": str(prefs.get("browserPermission") or "default").strip() or "default",
    }

def _normalize_recent_clusters(items):
    rows = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict): continue
        cluster_id = str(item.get("cluster_id") or "").strip()
        if not cluster_id or cluster_id in seen: continue
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
        if len(rows) >= 24: break
    return rows

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
    merged_recent = _normalize_recent_clusters(sorted(left["recentClusters"] + right["recentClusters"], key=lambda item: str(item.get("viewedAt") or ""), reverse=True))
    return {
        "followedTopics": _normalize_sync_list(left["followedTopics"] + right["followedTopics"], limit=12),
        "followedSources": _normalize_sync_list(left["followedSources"] + right["followedSources"], limit=12),
        "recentClusters": merged_recent,
        "deliveryPreferences": {**left["deliveryPreferences"], **right["deliveryPreferences"]},
    }

def _normalize_server_delivery_row(row):
    if not row: return _normalize_server_delivery_subscription({})
    return _normalize_server_delivery_subscription({
        "channel": row.get("channel"),
        "target": row.get("target"),
        "morningBriefing": row.get("morning_briefing"),
        "weeklyDigest": row.get("weekly_digest"),
        "breakingTopics": row.get("breaking_topics"),
        "breakingSources": row.get("breaking_sources"),
        "isActive": row.get("is_active"),
    })

@router.post("/profile/sync/init")
async def init_profile_sync():
    token = secrets.token_urlsafe(18)
    empty = _normalize_synced_profile({})
    db.execute("INSERT INTO synced_reader_profiles (sync_token, profile_data) VALUES (%s, %s::jsonb)", (token, json.dumps(empty)), fetch=False)
    return {"status": "success", "token": token, "profile": empty}

@router.get("/profile/sync")
async def get_profile_sync(request: Request):
    token = _extract_sync_token(request)
    if not token or len(token) < 12: raise HTTPException(status_code=400, detail="Missing sync token")
    row = db.execute_one("SELECT profile_data, updated_at FROM synced_reader_profiles WHERE sync_token = %s", (token,))
    if not row: raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success", "profile": _normalize_synced_profile(row.get("profile_data") or {}), "updated_at": row.get("updated_at")}

@router.post("/profile/sync")
async def save_profile_sync(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    token = str(payload.get("token") or "").strip()
    if not token: raise HTTPException(status_code=400, detail="Missing sync token")
    incoming = _normalize_synced_profile(payload.get("profile") or {})
    existing = db.execute_one("SELECT profile_data FROM synced_reader_profiles WHERE sync_token = %s", (token,))
    if not existing: raise HTTPException(status_code=404, detail="Profile not found")
    merged = _merge_synced_profiles(existing.get("profile_data") or {}, incoming)
    db.execute("UPDATE synced_reader_profiles SET profile_data = %s::jsonb, updated_at = NOW() WHERE sync_token = %s", (json.dumps(merged), token), fetch=False)
    return {"status": "success", "profile": merged}

@router.get("/profile/vapid-key")
async def get_vapid_key():
    from config import VAPID_PUBLIC_KEY
    if not VAPID_PUBLIC_KEY: raise HTTPException(status_code=404, detail="Web Push not configured")
    return {"status": "success", "key": VAPID_PUBLIC_KEY}

@router.get("/profile/delivery")
async def get_profile_delivery(request: Request):
    token = _extract_sync_token(request)
    if not token: raise HTTPException(status_code=400, detail="Missing sync token")
    # Validate token length
    if len(token) < 12:
        raise HTTPException(status_code=400, detail="Invalid sync token format")
    row = db.execute_one("SELECT * FROM synced_delivery_subscriptions WHERE sync_token = %s", (token,))
    return {"status": "success", "subscription": _normalize_server_delivery_row(row), "updated_at": row.get("updated_at") if row else None}

@router.post("/profile/delivery")
async def save_profile_delivery(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    token = str(payload.get("token") or "").strip()
    if not token: raise HTTPException(status_code=400, detail="Missing sync token")
    # Validate token length
    if len(token) < 12:
        raise HTTPException(status_code=400, detail="Invalid sync token format")
    if not db.execute_one("SELECT 1 FROM synced_reader_profiles WHERE sync_token = %s", (token,)):
        raise HTTPException(status_code=400, detail="Invalid sync token")
    sub = _normalize_server_delivery_subscription(payload.get("subscription") or {})
    db.execute("""INSERT INTO synced_delivery_subscriptions
           (sync_token, channel, target, morning_briefing, weekly_digest, breaking_topics, breaking_sources, is_active, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
           ON CONFLICT (sync_token) DO UPDATE SET
             channel=EXCLUDED.channel, target=EXCLUDED.target, morning_briefing=EXCLUDED.morning_briefing,
             weekly_digest=EXCLUDED.weekly_digest, breaking_topics=EXCLUDED.breaking_topics,
             breaking_sources=EXCLUDED.breaking_sources, is_active=EXCLUDED.is_active, updated_at=NOW()""",
        (token, sub["channel"], sub["target"], sub["morningBriefing"], sub["weeklyDigest"], sub["breakingTopics"], sub["breakingSources"], sub["isActive"]), fetch=False)
    return {"status": "success", "subscription": sub}

@router.post("/profile/sync/personalized-news")
async def get_personalized_news_sync(request: Request):
    """
    Takes a profile payload, calculates the semantic interest vector 
    of the user and returns semantically relevant clusters from the last 48h.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    profile = _normalize_synced_profile(payload.get("profile") or {})
    recent = profile.get("recentClusters") or []
    if not recent:
        return {"status": "success", "results": []}

    # 1. Fetch embeddings for recent clusters
    recent_ids = [r['cluster_id'] for r in recent[:10]] # Limit to last 10 for speed
    vec_rows = await db.async_execute("SELECT embedding FROM articles WHERE cluster_id = ANY(%s) AND embedding IS NOT NULL", (recent_ids,))
    
    if not vec_rows:
        return {"status": "success", "results": []}

    import numpy as np
    def parse_vec(v):
        if isinstance(v, str):
            import json
            v = json.loads(v)
        return np.array(v, dtype=np.float32)

    vecs = [parse_vec(r['embedding']) for r in vec_rows]
    interest_vec = np.mean(vecs, axis=0).tolist()
    vec_str = "[" + ",".join(map(str, interest_vec)) + "]"

    limit = payload.get("limit") or 6
    try:
        limit = min(max(int(limit), 1), 48)
    except:
        limit = 6

    # 2. Semantic Search for similar news in last 72 hours (expanded window)
    # Exclude already seen clusters
    rows = await db.async_execute("""
        WITH pool AS (
            SELECT cluster_id, title, source, created_at, category, topic, is_global, is_fact_check,
                   (1 - (embedding <=> %s::vector)) as similarity
            FROM articles
            WHERE created_at >= NOW() - INTERVAL '72 hours'
              AND cluster_id != ALL(%s)
              AND embedding IS NOT NULL
        )
        SELECT DISTINCT ON (cluster_id) *
        FROM pool
        WHERE similarity > 0.55
        ORDER BY cluster_id, similarity DESC
        LIMIT 100
    """, (vec_str, recent_ids))

    # 3. Group and annotate
    from .news import _public_article_payload
    from collections import defaultdict
    
    clusters = defaultdict(list)
    for r in rows:
        clusters[r['cluster_id']].append(r)

    # 4. Fetch all articles for these clusters to build complete NewsClusters
    cids = list(clusters.keys())
    if not cids:
        return {"status": "success", "results": []}

    all_articles = await db.async_execute("SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY created_at DESC", (cids,))
    meta_rows = await db.async_execute("SELECT * FROM cluster_metadata WHERE cluster_id = ANY(%s)", (cids,))
    synthesis_ids = set(await db.async_get_synthesis_ids(cids))
    
    meta_map = {r['cluster_id']: r for r in meta_rows}
    cluster_articles = defaultdict(list)
    for a in all_articles:
        cluster_articles[a['cluster_id']].append(a)

    results = []
    # Rank by original similarity
    sorted_cids = sorted(cids, key=lambda cid: clusters[cid][0]['similarity'], reverse=True)
    
    for cid in sorted_cids[:limit]:
        arts = cluster_articles[cid]
        if not arts: continue
        
        main = arts[0]
        annotated = annotate_cluster_articles(arts)
        meta = meta_map.get(cid) or {}
        score = score_cluster(arts)
        
        results.append({
            "cluster_id": cid,
            "articles": [_public_article_payload(a) for a in annotated],
            "representative_image": meta.get("representative_image"),
            "dominant_color": meta.get("dominant_color"),
            "is_breaking": score >= BREAKING_SCORE_THRESHOLD,
            "has_synthesis": cid in synthesis_ids,
            "has_balanced": is_balanced(arts),
            "score": round(score, 3),
            "homepage_score": round(score_cluster_for_homepage(arts), 3),
            "similarity": round(float(clusters[cid][0]['similarity']), 4),
            "reason": "Поврзано со вашите интереси"
        })

    return {"status": "success", "results": results}

@router.post("/profile/suggestion-event")
async def save_suggestion_events(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    token = str(payload.get("token") or "").strip()
    client_id = str(payload.get("clientId") or "").strip()[:64]
    events = payload.get("events") or []
    if not client_id or not events: raise HTTPException(status_code=400, detail="Missing data")
    # Validate client_id
    if len(client_id) < 1 or len(client_id) > 64:
        raise HTTPException(status_code=400, detail="Invalid client ID")
    for item in events[:24]:
        surface = _normalize_suggestion_surface(item.get("surface"))
        etype = _normalize_suggestion_event_type(item.get("eventType"))
        kind = _normalize_suggestion_kind(item.get("suggestionKind"))
        val = str(item.get("value") or "").strip()[:160]
        if surface and etype:
            db.execute("INSERT INTO suggestion_surface_events (sync_token, client_id, surface, suggestion_kind, event_type, value, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                (token or None, client_id, surface, kind or None, etype, val, json.dumps({})), fetch=False)
    delete_cache("stats:full")
    return {"status": "success"}
