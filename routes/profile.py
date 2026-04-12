import json
import secrets
import logging
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException

from database import db_manager as db
from utils import delete_cache
from api_helpers import normalize_server_delivery_subscription as _normalize_server_delivery_subscription
from .common import _normalize_sync_list, _extract_sync_token, _normalize_suggestion_surface, _normalize_suggestion_kind, _normalize_suggestion_event_type

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

@router.post("/api/profile/sync/init")
async def init_profile_sync():
    token = secrets.token_urlsafe(18)
    empty = _normalize_synced_profile({})
    db.execute("INSERT INTO synced_reader_profiles (sync_token, profile_data) VALUES (%s, %s::jsonb)", (token, json.dumps(empty)), fetch=False)
    return {"status": "success", "token": token, "profile": empty}

@router.get("/api/profile/sync")
async def get_profile_sync(request: Request):
    token = _extract_sync_token(request)
    if not token or len(token) < 12: raise HTTPException(status_code=400, detail="Missing sync token")
    row = db.execute_one("SELECT profile_data, updated_at FROM synced_reader_profiles WHERE sync_token = %s", (token,))
    if not row: raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success", "profile": _normalize_synced_profile(row.get("profile_data") or {}), "updated_at": row.get("updated_at")}

@router.post("/api/profile/sync")
async def save_profile_sync(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    if not token: raise HTTPException(status_code=400, detail="Missing sync token")
    incoming = _normalize_synced_profile(payload.get("profile") or {})
    existing = db.execute_one("SELECT profile_data FROM synced_reader_profiles WHERE sync_token = %s", (token,))
    if not existing: raise HTTPException(status_code=404, detail="Profile not found")
    merged = _merge_synced_profiles(existing.get("profile_data") or {}, incoming)
    db.execute("UPDATE synced_reader_profiles SET profile_data = %s::jsonb, updated_at = NOW() WHERE sync_token = %s", (json.dumps(merged), token), fetch=False)
    return {"status": "success", "profile": merged}

@router.get("/api/profile/vapid-key")
async def get_vapid_key():
    from config import VAPID_PUBLIC_KEY
    if not VAPID_PUBLIC_KEY: raise HTTPException(status_code=404, detail="Web Push not configured")
    return {"status": "success", "key": VAPID_PUBLIC_KEY}

@router.get("/api/profile/delivery")
async def get_profile_delivery(request: Request):
    token = _extract_sync_token(request)
    if not token: raise HTTPException(status_code=400, detail="Missing sync token")
    row = db.execute_one("SELECT * FROM synced_delivery_subscriptions WHERE sync_token = %s", (token,))
    return {"status": "success", "subscription": _normalize_server_delivery_row(row), "updated_at": row.get("updated_at") if row else None}

@router.post("/api/profile/delivery")
async def save_profile_delivery(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    if not token: raise HTTPException(status_code=400, detail="Missing sync token")
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

@router.post("/api/profile/suggestion-event")
async def save_suggestion_events(request: Request):
    payload = await request.json()
    token = str(payload.get("token") or "").strip()
    client_id = str(payload.get("clientId") or "").strip()[:64]
    events = payload.get("events") or []
    if not client_id or not events: raise HTTPException(status_code=400, detail="Missing data")
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
