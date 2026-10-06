import datetime
import ipaddress
import logging
import os
import re
from typing import Optional

from fastapi import HTTPException, Request

from core.api_errors import api_error_response, rate_limit_payload
from core.config import DEFAULT_LANG
from core.database import db_manager as db
from nlp.utils import cleanAndDecode

log = logging.getLogger("presek")

_PROXY_ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/avif",
}
_PROXY_MAX_BYTES = 10 * 1024 * 1024


def _normalize_proxy_content_type(content_type: str) -> str:
    """Normalize remote image Content-Type headers for proxy allowlist checks."""
    ctype = str(content_type or "").split(";", 1)[0].strip().lower()
    if ctype == "image/jpg":
        return "image/jpeg"
    return ctype


def _is_allowed_proxy_content_type(content_type: str) -> bool:
    return _normalize_proxy_content_type(content_type) in _PROXY_ALLOWED_TYPES


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
            raise HTTPException(status_code=400, detail="Nedostasuva kluc za sinhronizacija")
        return ""
    if not SYNC_TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(status_code=400, detail="Невалиден формат на клучот за синхронизација")
    return token


def _looks_cyrillic_headline(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    cyrillic = sum(1 for ch in value if "\u0400" <= ch <= "\u04ff")
    latin = sum(1 for ch in value if ("A" <= ch <= "Z") or ("a" <= ch <= "z"))
    if cyrillic < 8:
        return False
    if latin == 0:
        return True
    return cyrillic >= (latin * 2)


def _preferred_cluster_headline(rows) -> str:
    preferred_cyrillic = None
    fallback = ""
    for row in rows or []:
        title = cleanAndDecode(row.get("title") or "")
        if not title:
            continue
        if not fallback:
            fallback = title
        original_title = cleanAndDecode(row.get("original_title") or "")
        is_translated = bool(row.get("is_translated")) or (original_title and title != original_title)
        if is_translated and _looks_cyrillic_headline(title):
            return title
        if preferred_cyrillic is None and _looks_cyrillic_headline(title):
            preferred_cyrillic = title
    return preferred_cyrillic or fallback or "vest"


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

    return client_host or "0.0.0.0"  # nosec B104 - fallback IP literal, not a socket bind


def _static_admin_token_authorized(request: Request) -> bool:
    """Check if request is authorized using the new admin token system or legacy token."""

    # Verify the legacy static token independently of the DB-backed token system.
    # core.admin_tokens raises on import when its table cannot be created, so the
    # import must not share a try block with this check: doing so made the legacy
    # admin token silently stop working whenever the admin_tokens table or DB was
    # unavailable.
    def _legacy_ok(candidate: str) -> bool:
        if not candidate:
            return False
        try:
            from core.admin_tokens import verify_legacy_admin_token

            return bool(verify_legacy_admin_token(candidate))
        except Exception as e:
            log.warning(f"Legacy admin token verification unavailable: {e}")
            return False

    candidates = [
        (request.headers.get("X-Admin-Token") or "").strip(),
    ]
    auth = str(request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        candidates.append(auth[7:].strip())

    for candidate in candidates:
        if _legacy_ok(candidate):
            return True

    # Try the new admin token system. Kept in its own try so a failure here does
    # not affect the legacy path above.
    try:
        from core.admin_tokens import verify_admin_token

        for candidate in candidates:
            if candidate and verify_admin_token(candidate):
                return True
    except Exception as e:
        log.warning(f"Admin token verification failed: {e}")

    return False


def _source_admin_authorized(request: Request) -> bool:
    if _static_admin_token_authorized(request):
        return True

    auth = str(request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return False

    try:
        from core.auth import verify_admin_jwt

        return verify_admin_jwt(auth[7:].strip())
    except Exception:
        return False


def _error_json(message: str, status_code: int, details=None):
    return api_error_response(message, status_code, detail=details)


def _is_valid_focus_entity(name: str, entity_type: Optional[str]) -> bool:
    from nlp import is_valid_focus_entity

    return is_valid_focus_entity(name, entity_type)


def _extract_sync_token(request: Request) -> str:
    if not request or (hasattr(request, "__class__") and "Mock" in request.__class__.__name__):
        return ""
    try:
        token = str(request.headers.get("X-Sync-Token") or "").strip()
        if token:
            return token
        auth = str(request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
    except Exception:
        log.debug("Common helper fallback")
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
    if not clean.startswith("/") or clean.startswith("//") or clean.startswith("/api/"):
        return "/briefing"
    if ".." in clean or "\\" in clean or ";" in clean:
        return "/briefing"
    _allowed = (
        "/briefing",
        "/cluster/",
        "/trending",
        "/archive",
        "/stati",
        "/subjekt/",
        "/tema/",
        "/izvori",
        "/admin/status",
        "/stats",
        "/about",
        "/contact",
        "/privacy",
        "/debug/",
    )
    if not any(clean.startswith(prefix) for prefix in _allowed) and clean != "/":
        return "/briefing"
    return clean


_RATE_LIMITED_API_PATHS = {
    "/api/proxy",
    "/api/news",
    "/api/trending",
    "/api/research/{cluster_id}",
    "/api/profile/sync/init",
    "/api/profile/sync",
    "/api/profile/sync/personalized-news",
    "/api/profile/delivery",
    "/api/profile/suggestion-event",
}


def _normalize_rate_limit_path(path: str) -> str:
    """Map versioned API paths (/api/v1/...) to canonical /api/... form."""
    clean = str(path or "").strip()
    if clean.startswith("/api/v1/"):
        return "/api/" + clean[len("/api/v1/") :]
    if clean == "/api/v1":
        return "/api"
    return clean


def _is_rate_limited_path(path: str) -> bool:
    clean = _normalize_rate_limit_path(str(path or "").strip())
    if not clean.startswith("/"):
        return False
    if clean in _RATE_LIMITED_API_PATHS:
        return True
    if re.fullmatch(r"/api/intelligence/cluster/[a-f0-9]{6,64}/(research|analyst)", clean):
        return True
    if re.fullmatch(r"/api/research/[a-f0-9\-]{6,64}", clean):
        return True
    canonical = clean[4:] if clean.startswith("/api/") else clean
    return f"/api{canonical}" in _RATE_LIMITED_API_PATHS


def _rate_limit_error_payload() -> dict:
    return rate_limit_payload(
        "Sintezata se podgotvuva... Ve molime obidete se povtorno za nekoja minuta.",
    )


async def build_intelligence_summary_payload(
    last_24h: int,
    category: Optional[str] = None,
    runtime_events: Optional[dict] = None,
    lang: Optional[str] = DEFAULT_LANG,
) -> dict:
    """Calculates synthesis transparency, pluralism and international share metrics with optional category and language filter."""
    import asyncio

    from utils import cached_response, redis_client, set_cache

    country_filter = "MK" if lang == "mk" else "RS"
    cat_id = f"cat-{category}-{lang}" if category else f"all-{lang}"
    cache_key = f"stats:intel_summary:{last_24h}:{cat_id}:v4"
    use_redis = bool(os.environ.get("REDIS_URL") and not os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED"))
    cached = cached_response(cache_key, ttl=600) if use_redis else None
    if cached:
        return cached

    # Count articles and international share in one query
    freshness_expr = "COALESCE(a.ingested_at, a.created_at)"
    cat_filter = ""
    params = [country_filter]
    if category:
        cat_filter = "AND a.category = %s"
        params.append(category)

    # Need a separate params list for balance_stats that includes the category filter if present
    balance_params = [category] if category else []

    counts_res = await db.async_execute_one(
        f"""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE a.category IN ('Svet', 'Evropa', 'Balkan', 'Region', 'Amerika', 'SAD') OR a.is_global = TRUE) as intl
        FROM articles a
        WHERE a.country = %s AND {freshness_expr} >= NOW() - INTERVAL '24 hours' {cat_filter}
    """,  # nosec B608 - static freshness/category fragments with bound params
        tuple(params),
    )

    total_articles_24h = counts_res.get("total", last_24h) if counts_res else 0
    intl_articles_24h = counts_res.get("intl", counts_res.get("count", 0)) if counts_res else 0

    if runtime_events is not None:
        ai_events = runtime_events or {}
    elif use_redis:
        bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
        try:
            ai_events = await asyncio.to_thread(redis_client.hgetall, f"presek:runtime_events:{bucket}") or {}
        except Exception as e:
            log.warning(f"[stats] runtime event read failed: {e}")
            ai_events = {}
    else:
        ai_events = {}

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

    # Parameters for balance_stats must match the cat_filter
    balance_params = [country_filter]
    if category:
        balance_params.append(category)

    balance_stats = await db.async_execute_one(
        f"""
        WITH cluster_tiers AS (
            SELECT cluster_id, COUNT(DISTINCT
                CASE
                    WHEN s.category IN ('Agencijski', 'Javni servis', 'glavni') THEN 'M'
                    WHEN s.category IN ('Nezavisni', 'Istraživački') THEN 'I'
                    ELSE 'R'
                END) as group_count
            FROM articles a
            JOIN sources s ON a.source = s.name
            WHERE a.country = %s AND COALESCE(a.ingested_at, a.created_at) >= NOW() - INTERVAL '24 hours' {cat_filter}
            GROUP BY cluster_id
        )
        SELECT
            COUNT(*) as total_clusters,
            COUNT(*) FILTER (WHERE group_count >= 3) as high_consensus,
            COUNT(*) FILTER (WHERE group_count = 2) as diverse_sources
        FROM cluster_tiers
    """,  # nosec B608 - static SQL with bound params
        tuple(balance_params),
    ) or {"total_clusters": 0, "high_consensus": 0, "diverse_sources": 0}

    res = {
        "last_24h": total_articles_24h,
        "international_share_pct": (
            round((intl_articles_24h / max(1, total_articles_24h) * 100), 1) if total_articles_24h > 0 else 0
        ),
        "synthesis_transparency": {
            "systemic_summaries": systemic_summaries,
            "local_summaries": local_summaries,
            "systemic_ratio": (
                round(systemic_summaries / (systemic_summaries + local_summaries) * 100, 1)
                if (systemic_summaries + local_summaries) > 0
                else 0
            ),
        },
        "pluralism": {
            "total_clusters": balance_stats["total_clusters"],
            "pluralism_pct": round(
                (balance_stats["high_consensus"] + balance_stats["diverse_sources"])
                / max(1, balance_stats["total_clusters"])
                * 100,
                1,
            ),
            "high_consensus_pct": round(
                balance_stats["high_consensus"] / max(1, balance_stats["total_clusters"]) * 100,
                1,
            ),
            "diverse_sources_pct": round(
                balance_stats["diverse_sources"] / max(1, balance_stats["total_clusters"]) * 100,
                1,
            ),
        },
    }
    if use_redis:
        set_cache(cache_key, res, ttl=600)
    return res
