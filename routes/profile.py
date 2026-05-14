import json
import secrets
import logging
from pydantic import BaseModel
from typing import List
from fastapi import APIRouter, Request, HTTPException

from database import db_manager as db
from utils import (
    delete_cache,
    score_cluster,
    is_balanced,
    score_cluster_for_homepage,
    annotate_cluster_articles,
)
from config import BREAKING_SCORE_THRESHOLD
from api_helpers import (
    normalize_server_delivery_subscription as _normalize_server_delivery_subscription,
)
from .common import (
    _normalize_sync_list,
    _extract_sync_token,
    _normalize_suggestion_surface,
    _normalize_suggestion_kind,
    _normalize_suggestion_event_type,
    _validate_sync_token_value,
)

log = logging.getLogger("presek")
router = APIRouter()


class DeliveryPreferences(BaseModel):
    morningBriefing: bool = True
    breakingAlerts: bool = True
    browserPermission: str = "default"


class RecentCluster(BaseModel):
    cluster_id: str
    title: str
    category: str
    topic: str
    primarySource: str
    sources: List[str]
    tags: List[str]
    viewedAt: str


class SyncedProfile(BaseModel):
    followedTopics: List[str]
    followedSources: List[str]
    recentClusters: List[RecentCluster]
    deliveryPreferences: DeliveryPreferences


class ProfileInitResponse(BaseModel):
    status: str
    sync_token: str
    token: str
    profile: SyncedProfile


class ProfileGetResponse(BaseModel):
    status: str
    profile: SyncedProfile


_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"


async def _prune_recent_clusters(items):
    recent = _normalize_recent_clusters(items)
    if not recent:
        return []

    cluster_ids = [item["cluster_id"] for item in recent]
    rows = await db.async_execute(
        "SELECT DISTINCT cluster_id FROM articles WHERE cluster_id = ANY(%s)",
        (cluster_ids,),
    )
    valid_ids = {
        str(row.get("cluster_id") or "").strip()
        for row in rows
        if row.get("cluster_id")
    }
    return [item for item in recent if item["cluster_id"] in valid_ids]


def _normalize_delivery_preferences(prefs):
    prefs = prefs or {}
    return {
        "morningBriefing": prefs.get("morningBriefing") is not False,
        "breakingAlerts": prefs.get("breakingAlerts") is not False,
        "browserPermission": str(prefs.get("browserPermission") or "default").strip()
        or "default",
    }


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
        rows.append(
            {
                "cluster_id": cluster_id,
                "title": str(item.get("title") or "").strip(),
                "category": str(item.get("category") or "").strip(),
                "topic": str(item.get("topic") or "").strip(),
                "primarySource": str(item.get("primarySource") or "").strip(),
                "sources": _normalize_sync_list(item.get("sources") or [], limit=8),
                "tags": _normalize_sync_list(item.get("tags") or [], limit=10),
                "viewedAt": str(item.get("viewedAt") or "").strip(),
            }
        )
        if len(rows) >= 24:
            break
    return rows


def _normalize_synced_profile(payload):
    payload = payload or {}
    return {
        "followedTopics": _normalize_sync_list(
            payload.get("followedTopics") or [], limit=12
        ),
        "followedSources": _normalize_sync_list(
            payload.get("followedSources") or [], limit=12
        ),
        "recentClusters": _normalize_recent_clusters(
            payload.get("recentClusters") or []
        ),
        "deliveryPreferences": _normalize_delivery_preferences(
            payload.get("deliveryPreferences") or {}
        ),
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
        "followedTopics": _normalize_sync_list(
            left["followedTopics"] + right["followedTopics"], limit=12
        ),
        "followedSources": _normalize_sync_list(
            left["followedSources"] + right["followedSources"], limit=12
        ),
        "recentClusters": merged_recent,
        "deliveryPreferences": {
            **left["deliveryPreferences"],
            **right["deliveryPreferences"],
        },
    }


def _normalize_server_delivery_row(row):
    if not row:
        return _normalize_server_delivery_subscription({})
    return _normalize_server_delivery_subscription(
        {
            "channel": row.get("channel"),
            "target": row.get("target"),
            "morningBriefing": row.get("morning_briefing"),
            "weeklyDigest": row.get("weekly_digest"),
            "breakingTopics": row.get("breaking_topics"),
            "breakingSources": row.get("breaking_sources"),
            "isActive": row.get("is_active"),
        }
    )


@router.post("/profile/sync/init", response_model=ProfileInitResponse)
async def init_profile_sync():
    token = _validate_sync_token_value(secrets.token_urlsafe(24))
    empty = _normalize_synced_profile({})
    await db.async_execute(
        "INSERT INTO synced_reader_profiles (sync_token, profile_data) VALUES (%s, %s::jsonb)",
        (token, json.dumps(empty)),
        fetch=False,
    )
    return {"status": "success", "sync_token": token, "token": token, "profile": empty}


@router.get("/profile/sync", response_model=ProfileGetResponse)
async def get_profile_sync(request: Request):
    token = _validate_sync_token_value(_extract_sync_token(request))
    row = await db.async_execute_one(
        "SELECT profile_data, updated_at FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Profil nije pronadjen")
    profile = _normalize_synced_profile(row.get("profile_data") or {})
    pruned_recent = await _prune_recent_clusters(profile.get("recentClusters") or [])
    if len(pruned_recent) != len(profile.get("recentClusters") or []):
        profile["recentClusters"] = pruned_recent
        await db.async_execute(
            "UPDATE synced_reader_profiles SET profile_data = %s::jsonb, updated_at = NOW() WHERE sync_token = %s",
            (json.dumps(profile), token),
            fetch=False,
        )
    return {
        "status": "success",
        "profile": profile,
        "updated_at": row.get("updated_at"),
    }


@router.post("/profile/sync")
async def save_profile_sync(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Nevaliden JSON")
    token = _validate_sync_token_value(payload.get("token"))
    incoming = _normalize_synced_profile(payload.get("profile") or {})
    existing = await db.async_execute_one(
        "SELECT profile_data FROM synced_reader_profiles WHERE sync_token = %s",
        (token,),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Profil nije pronadjen")
    merged = _merge_synced_profiles(existing.get("profile_data") or {}, incoming)
    merged["recentClusters"] = await _prune_recent_clusters(
        merged.get("recentClusters") or []
    )
    await db.async_execute(
        "UPDATE synced_reader_profiles SET profile_data = %s::jsonb, updated_at = NOW() WHERE sync_token = %s",
        (json.dumps(merged), token),
        fetch=False,
    )
    return {"status": "success", "profile": merged}


@router.get("/profile/vapid-key")
async def get_vapid_key():
    from config import VAPID_PUBLIC_KEY

    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=404, detail="Web Push nije konfigurisan")
    return {"status": "success", "key": VAPID_PUBLIC_KEY}


@router.get("/profile/delivery")
async def get_profile_delivery(request: Request):
    token = _validate_sync_token_value(_extract_sync_token(request))
    row = await db.async_execute_one(
        "SELECT * FROM synced_delivery_subscriptions WHERE sync_token = %s", (token,)
    )
    return {
        "status": "success",
        "subscription": _normalize_server_delivery_row(row),
        "updated_at": row.get("updated_at") if row else None,
    }


@router.post("/profile/delivery")
async def save_profile_delivery(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Nevaliden JSON")
    token = _validate_sync_token_value(payload.get("token"))
    if not await db.async_execute_one(
        "SELECT 1 FROM synced_reader_profiles WHERE sync_token = %s", (token,)
    ):
        raise HTTPException(status_code=400, detail="Nevaliden kluc za sinhronizacija")
    sub = _normalize_server_delivery_subscription(payload.get("subscription") or {})
    locale = str(payload.get("locale") or "sr").strip().lower()[:5]
    await db.async_execute(
        """INSERT INTO synced_delivery_subscriptions
           (sync_token, channel, target, morning_briefing, weekly_digest, breaking_topics, breaking_sources, is_active, locale, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
           ON CONFLICT (sync_token) DO UPDATE SET
             channel=EXCLUDED.channel, target=EXCLUDED.target, morning_briefing=EXCLUDED.morning_briefing,
             weekly_digest=EXCLUDED.weekly_digest, breaking_topics=EXCLUDED.breaking_topics,
             breaking_sources=EXCLUDED.breaking_sources, is_active=EXCLUDED.is_active,
             locale=EXCLUDED.locale, updated_at=NOW()""",
        (
            token,
            sub["channel"],
            sub["target"],
            sub["morningBriefing"],
            sub["weeklyDigest"],
            sub["breakingTopics"],
            sub["breakingSources"],
            sub["isActive"],
            locale,
        ),
        fetch=False,
    )
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
        raise HTTPException(status_code=400, detail="Nevaliden JSON")

    profile = _normalize_synced_profile(payload.get("profile") or {})
    recent = profile.get("recentClusters") or []

    # 1. Fetch embeddings for recent clusters
    recent_ids = [r["cluster_id"] for r in recent[:10]]  # Limit to last 10 for speed

    vec_rows = []
    if recent_ids:
        vec_rows = await db.async_execute(
            "SELECT embedding FROM articles WHERE cluster_id = ANY(%s) AND embedding IS NOT NULL",
            (recent_ids,),
        )

    # 1b. Fallback: If no recent clusters, use followed topics to find recent popular clusters as seeds
    if not vec_rows and profile.get("followedTopics"):
        topics = profile.get("followedTopics")
        seed_rows = await db.async_execute(
            """
            SELECT embedding FROM articles 
            WHERE (topic = ANY(%s) OR category = ANY(%s))
            AND created_at >= NOW() - INTERVAL '72 hours'
            AND embedding IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 20
        """,
            (topics, topics),
        )
        vec_rows = seed_rows

    if not vec_rows:
        return {"status": "success", "results": []}

    def parse_vec(v):
        if isinstance(v, str):
            import json

            v = json.loads(v)
        return [float(item) for item in v]

    vecs = [parse_vec(r["embedding"]) for r in vec_rows]
    dims = len(vecs[0]) if vecs else 0
    interest_vec = [sum(vec[idx] for vec in vecs) / len(vecs) for idx in range(dims)]
    vec_str = "[" + ",".join(map(str, interest_vec)) + "]"

    limit = payload.get("limit") or 6
    try:
        limit = min(max(int(limit), 1), 48)
    except (ValueError, TypeError):
        limit = 6

    # 2. Semantic Search for similar news in last 72 hours (expanded window)
    # Exclude already seen clusters
    rows = await db.async_execute(
        f"""
        WITH pool AS (
            SELECT cluster_id, title, source, created_at, ingested_at, category, topic, is_global, is_fact_check,
                   (1 - (embedding <=> %s::vector)) as similarity
            FROM articles
            WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '72 hours'
              AND cluster_id NOT IN (SELECT unnest(%s::text[]))
              AND embedding IS NOT NULL
        )
        SELECT DISTINCT ON (cluster_id) *
        FROM pool
        WHERE similarity > 0.55
        ORDER BY cluster_id, similarity DESC
        LIMIT 100
    """,
        (vec_str, recent_ids),
    )

    # 3. Group and annotate
    from .news import _public_article_payload
    from collections import defaultdict

    clusters = defaultdict(list)
    for r in rows:
        clusters[r["cluster_id"]].append(r)

    # 4. Fetch all articles for these clusters to build complete NewsClusters
    cids = list(clusters.keys())
    if not cids:
        return {"status": "success", "results": []}

    all_articles = await db.async_execute(
        f"SELECT * FROM articles WHERE cluster_id = ANY(%s) ORDER BY {_FRESHNESS_EXPR} DESC, created_at DESC",
        (cids,),
    )
    meta_rows = await db.async_execute(
        "SELECT * FROM cluster_metadata WHERE cluster_id = ANY(%s)", (cids,)
    )
    synthesis_ids = set(await db.async_get_synthesis_ids(cids))

    meta_map = {r["cluster_id"]: r for r in meta_rows}
    cluster_articles = defaultdict(list)
    for a in all_articles:
        cluster_articles[a["cluster_id"]].append(a)

    results = []
    # Rank by original similarity
    sorted_cids = sorted(
        cids, key=lambda cid: clusters[cid][0]["similarity"], reverse=True
    )

    for cid in sorted_cids[:limit]:
        arts = cluster_articles[cid]
        if not arts:
            continue

        annotated = annotate_cluster_articles(arts)
        meta = meta_map.get(cid) or {}
        score = score_cluster(arts)

        results.append(
            {
                "cluster_id": cid,
                "articles": [_public_article_payload(a) for a in annotated],
                "representative_image": meta.get("representative_image"),
                "dominant_color": meta.get("dominant_color"),
                "is_breaking": score >= BREAKING_SCORE_THRESHOLD,
                "has_synthesis": cid in synthesis_ids,
                "has_balanced": is_balanced(arts),
                "score": round(score, 3),
                "homepage_score": round(score_cluster_for_homepage(arts), 3),
                "similarity": round(float(clusters[cid][0]["similarity"]), 4),
                "reason": "Povrzano so vasite interesi",
            }
        )

    return {"status": "success", "results": results}


@router.post("/profile/suggestion-event")
async def save_suggestion_events(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Nevaliden JSON")
    token = str(payload.get("token") or "").strip()
    client_id = str(payload.get("clientId") or "").strip()[:64]
    events = payload.get("events") or []
    if not client_id or not events:
        raise HTTPException(status_code=400, detail="Nedostasuvaat podatoci")
    # Validate client_id
    if len(client_id) < 1 or len(client_id) > 64:
        raise HTTPException(status_code=400, detail="Nevaliden klient ID")
    for item in events[:24]:
        surface = _normalize_suggestion_surface(item.get("surface"))
        etype = _normalize_suggestion_event_type(item.get("eventType"))
        kind = _normalize_suggestion_kind(item.get("suggestionKind"))
        val = str(item.get("value") or "").strip()[:160]
        if surface and etype:
            await db.async_execute(
                "INSERT INTO suggestion_surface_events (sync_token, client_id, surface, suggestion_kind, event_type, value, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    token or None,
                    client_id,
                    surface,
                    kind or None,
                    etype,
                    val,
                    json.dumps({}),
                ),
                fetch=False,
            )
    delete_cache("stats:full")
    return {"status": "success"}
