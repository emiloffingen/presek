import os
import secrets
import json
import logging
import datetime
import time
import re
import ipaddress
import html as _html
import urllib.request
import urllib.parse
import socket
from typing import Optional, List
from pathlib import Path
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from database import db_manager as db
from config import API_MAX_Q_LEN
from utils import _resolve_public_ips, _peer_ip
from nlp.utils import cleanAndDecode

log = logging.getLogger("presek")

_PROXY_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}
_PROXY_MAX_BYTES = 10 * 1024 * 1024
SYNC_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")

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


def _validate_sync_token_value(value: str, *, required: bool = True) -> str:
    token = str(value or "").strip()
    if not token:
        if required:
            raise HTTPException(status_code=400, detail="Недостасува клуч за синхронизација")
        return ""
    if not SYNC_TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(status_code=400, detail="Невалиден формат на клучот за синхронизација")
    return token

def _looks_macedonian_headline(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    cyrillic = sum(1 for ch in value if "\u0400" <= ch <= "\u04FF")
    latin = sum(1 for ch in value if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if cyrillic < 8:
        return False
    if latin == 0:
        return True
    return cyrillic >= (latin * 2)

def _preferred_cluster_headline(rows) -> str:
    preferred_mk = None
    fallback = ""
    for row in rows or []:
        title = cleanAndDecode(row.get("title") or "")
        if not title:
            continue
        if not fallback:
            fallback = title
        original_title = cleanAndDecode(row.get("original_title") or "")
        is_translated = bool(row.get("is_translated")) or (original_title and title != original_title)
        if is_translated and _looks_macedonian_headline(title):
            return title
        if preferred_mk is None and _looks_macedonian_headline(title):
            preferred_mk = title
    return preferred_mk or fallback or "Вест"

def _parse_ip_literal(value: str) -> str:
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return ""


def _trusted_proxy_networks():
    """Return the configured proxy CIDRs allowed to supply forwarding headers."""
    raw = os.environ.get("TRUSTED_PROXY_CIDRS", "").strip()
    cidrs = [item.strip() for item in raw.split(",") if item.strip()]
    if not cidrs:
        cidrs = ["127.0.0.1/32", "::1/128"]

    networks = []
    for cidr in cidrs:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            log.warning("Ignoring invalid TRUSTED_PROXY_CIDRS entry: %s", cidr)
    return networks


def _is_trusted_proxy_ip(client_host: str) -> bool:
    try:
        addr = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    return any(addr in network for network in _trusted_proxy_networks())

def _client_ip_for_request(request: Request) -> str:
    """Extract the best-guess client IP address from known trusted proxies only."""
    client_host = _parse_ip_literal(str(getattr(getattr(request, "client", None), "host", "") or ""))

    if _is_trusted_proxy_ip(client_host):
        # Trust X-Real-IP or the first entry in X-Forwarded-For
        real_ip = _parse_ip_literal((request.headers.get("X-Real-IP") or "").split(",")[0].strip())
        if not real_ip:
            real_ip = _parse_ip_literal((request.headers.get("X-Forwarded-For") or "").split(",")[0].strip())
        if real_ip:
            return real_ip

    return client_host or "0.0.0.0"

def _source_admin_authorized(request: Request) -> bool:
    token = (request.headers.get("X-Admin-Token") or "").strip()
    expected = (os.environ.get("PRESEK_ADMIN_TOKEN") or "").strip()
    client_host = _client_ip_for_request(request)
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").strip()
    if not expected:
        return client_host in {"127.0.0.1", "::1"} and not forwarded_for
    if not token:
        return False
    return secrets.compare_digest(token, expected)

def _apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https: blob: https://www.google-analytics.com https://www.googletagmanager.com; "
        "connect-src 'self' https: https://www.google-analytics.com https://analytics.google.com; "
        "frame-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    return response

def _error_json(message: str, status_code: int, details=None):
    payload = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def _is_valid_focus_entity(name: str, entity_type: Optional[str]) -> bool:
    from nlp import is_valid_focus_entity
    return is_valid_focus_entity(name, entity_type)

def _extract_sync_token(request: Request) -> str:
    token = str(request.headers.get("X-Sync-Token") or "").strip()
    if token: return token
    auth = str(request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "): return auth[7:].strip()
    return ""

def _news_row_limit(page: int, page_size: int) -> int:
    return min(max((page + 1) * page_size * 12, 200), 2000)

def _normalize_suggestion_surface(value: str) -> str:
    return re.sub(r"[^a-z0-9_:-]+", "_", str(value or "").strip().lower())

def _normalize_suggestion_kind(value: str) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in {"topic", "source"} else ""

def _normalize_suggestion_event_type(value: str) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in {"impression", "follow", "dismiss"} else ""

def _safe_tracking_redirect_path(path: str) -> str:
    clean = str(path or "").strip()
    if not clean.startswith("/") or clean.startswith("//") or clean.startswith("/api/"): return "/briefing"
    if ".." in clean or "\\" in clean or ";" in clean: return "/briefing"
    _allowed = ("/briefing", "/cluster/", "/trending", "/archive", "/stati", "/subjekt/", "/tema/", "/izvori", "/admin/status", "/stats", "/about", "/contact", "/privacy", "/debug/")
    if not any(clean.startswith(prefix) for prefix in _allowed) and clean != "/": return "/briefing"
    return clean

_RATE_LIMITED_API_PATHS = {
    "/api/news",
    "/api/trending",
    "/api/intelligence/cluster/{cluster_id}/research",
    "/api/intelligence/cluster/{cluster_id}/analyst",
    "/api/intelligence/top-entities",
    "/api/profile/sync/init",
    "/api/profile/sync",
    "/api/profile/sync/personalized-news",
    "/api/profile/delivery",
    "/api/profile/suggestion-event",
}

def _is_rate_limited_path(path: str) -> bool:
    clean = str(path or "").strip()
    if not clean.startswith("/"):
        return False
    if clean in _RATE_LIMITED_API_PATHS:
        return True
    if re.fullmatch(r"/api/intelligence/cluster/[a-f0-9]{6,64}/(research|analyst)", clean):
        return True
    canonical = clean[4:] if clean.startswith("/api/") else clean
    return f"/api{canonical}" in _RATE_LIMITED_API_PATHS

def _rate_limit_error_payload() -> dict:
    return {"error": "Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута."}

async def build_intelligence_summary_payload(last_24h: int, category: Optional[str] = None) -> dict:
    """Calculates synthesis transparency, pluralism and international share metrics with optional category filter."""
    from utils import cached_response, set_cache, redis_client
    import asyncio
    
    cat_id = f"cat-{category}" if category else "all"
    cache_key = f"stats:intel_summary:{last_24h}:{cat_id}:v3"
    cached = cached_response(cache_key, ttl=300)
    if cached: return cached

    # Count international articles based on categories since is_global flag is unreliable
    freshness_expr = "COALESCE(ingested_at, created_at)"
    cat_filter = ""
    params = []
    if category:
        cat_filter = "AND category = %s"
        params.append(category)

    total_articles_24h_res = await db.async_execute_one(f"SELECT COUNT(*) FROM articles WHERE {freshness_expr} >= NOW() - INTERVAL '24 hours' {cat_filter}", tuple(params))
    total_articles_24h = total_articles_24h_res["count"] if total_articles_24h_res else 0

    intl_articles_24h_res = await db.async_execute_one(f"""
        SELECT COUNT(*) FROM articles 
        WHERE {freshness_expr} >= NOW() - INTERVAL '24 hours' {cat_filter}
          AND (category IN ('Свет', 'Европа', 'Балкан', 'Регион', 'Америка', 'САД') OR is_global = TRUE)
    """, tuple(params))
    intl_articles_24h = intl_articles_24h_res["count"] if intl_articles_24h_res else 0

    bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    ai_events = await asyncio.to_thread(redis_client.hgetall, f"presek:runtime_events:{bucket}") or {}
    
    # Robustly count summaries (Systemic vs Local)
    # Note: Runtime events are global, not per-category for now
    systemic_summaries = 0
    local_summaries = 0
    
    for k, v in ai_events.items():
        key = k.decode() if isinstance(k, bytes) else k
        if key.startswith("synthesis_path") or key.startswith("summary_path"):
            val = int(v)
            if "mode=local" in key:
                local_summaries += val
            else:
                systemic_summaries += val

    balance_stats = await db.async_execute_one(f"""
        WITH cluster_tiers AS (
            SELECT cluster_id, COUNT(DISTINCT
                CASE
                    WHEN s.category IN ('Агенциски', 'Јавен Сервис', 'Главни') THEN 'M'
                    WHEN s.category IN ('Независни', 'Истражувачки') THEN 'I'
                    ELSE 'R'
                END) as group_count
            FROM articles a
            JOIN sources s ON a.source = s.name
            WHERE COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '24 hours' {cat_filter}
            GROUP BY cluster_id
        )
        SELECT
            COUNT(*) as total_clusters,
            COUNT(*) FILTER (WHERE group_count >= 3) as high_consensus,
            COUNT(*) FILTER (WHERE group_count = 2) as diverse_sources
        FROM cluster_tiers
    """, tuple(params)) or {"total_clusters": 0, "high_consensus": 0, "diverse_sources": 0}

    res = {
        "last_24h": total_articles_24h,
        "international_share_pct": round((intl_articles_24h / max(1, total_articles_24h) * 100), 1) if total_articles_24h > 0 else 0,
        "synthesis_transparency": {
            "systemic_summaries": systemic_summaries,
            "local_summaries": local_summaries,
            "systemic_ratio": round(systemic_summaries / (systemic_summaries + local_summaries) * 100, 1) if (systemic_summaries + local_summaries) > 0 else 0
        },
        "pluralism": {
            "total_clusters": balance_stats["total_clusters"],
            "pluralism_pct": round((balance_stats["high_consensus"] + balance_stats["diverse_sources"]) / max(1, balance_stats["total_clusters"]) * 100, 1),
            "high_consensus_pct": round(balance_stats["high_consensus"] / max(1, balance_stats["total_clusters"]) * 100, 1),
            "diverse_sources_pct": round(balance_stats["diverse_sources"] / max(1, balance_stats["total_clusters"]) * 100, 1)
        }
    }
    set_cache(cache_key, res, ttl=300)
    return res
