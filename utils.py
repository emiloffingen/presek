import datetime
import asyncio
import logging
import math
import redis
import json
import os
import time
import urllib.request
from PIL import Image
from io import BytesIO
import requests
from config import (
    SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY, SOURCE_CATEGORIES
)

log = logging.getLogger("presek")
redis_client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
_SOURCE_STATUS_CACHE = {"time": 0.0, "data": {}}

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects."""
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            # Append Z to indicate UTC if it's naive, or use isoformat as-is if already aware
            if isinstance(obj, datetime.datetime) and obj.tzinfo is None:
                return obj.isoformat() + "Z"
            return obj.isoformat()
        return super().default(obj)

def get_dominant_color(url: str) -> str:
    """Extracts the dominant hex color from an image URL."""
    if not url: return ""
    
    # Recursion Guard: Prevent the system from calling its own proxy to extract colors
    # which can lead to infinite request loops and worker exhaustion.
    internal_proxy_markers = ["/api/proxy", "presek.live/proxy", "localhost:5001/proxy", "api:5001/proxy"]
    if any(marker in url for marker in internal_proxy_markers):
        log.warning(f"[utils] color extraction blocked for recursive/internal URL: {url}")
        return ""

    if not url.startswith("http"):
        if url.startswith("/static/"):
            return ""
        return ""

    try:
        import httpx
        try:
            import pillow_avif
        except ImportError:
            pass

        # Use a dedicated timeout and restrict redirects to prevent SSRF/DoS
        with httpx.Client(timeout=4.0, follow_redirects=True, max_redirects=2) as client:
            # Security: Resolve IPs first to prevent DNS Rebinding/SSRF
            try:
                safe_ips = _resolve_public_ips(url)
            except Exception:
                return ""
            
            response = client.get(url, headers={"User-Agent": "PresekColorBot/1.0"})
            
            # Post-connection IP verification
            p_ip = _peer_ip(response)
            if not p_ip or p_ip not in safe_ips:
                log.warning(f"[utils] color extraction blocked: IP mismatch/private for {url}")
                return ""

        if response.status_code != 200: return ""

        img = Image.open(BytesIO(response.content))
        img = img.convert("RGB")
        img.thumbnail((60, 60)) # Reduced size for speed
        
        colors = img.getcolors(3600)
        if not colors: return ""
        
        def is_usable(rgb):
            r, g, b = rgb
            if r > 245 and g > 245 and b > 245: return False
            if r < 15 and g < 15 and b < 15: return False
            avg = (r + g + b) / 3
            if abs(r-avg) < 12 and abs(g-avg) < 12 and abs(b-avg) < 12: return False
            return True

        sorted_colors = sorted(colors, key=lambda x: x[0], reverse=True)
        usable = [c for c in sorted_colors if is_usable(c[1])]
        dominant = usable[0][1] if usable else sorted_colors[0][1]
            
        return '#{:02x}{:02x}{:02x}'.format(*dominant)
    except Exception as e:
        log.debug(f"[utils] color extraction failed for {url}: {e}")
        return ""

_CACHE_MISS = object()  # sentinel to distinguish cache miss from Redis error

def cached_response(key: str, ttl: int = 60):
    """Read a cached JSON value from Redis.
    Returns None on cache miss or Redis error (fail-open)."""
    try:
        val = redis_client.get(key)
        if val:
            return json.loads(val)
    except redis.ConnectionError:
        log.error(f"[cache] Redis connection lost reading {key}")
    except Exception as e:
        log.warning(f"[cache] redis read error on {key}: {e}")
    return None

def set_cache(key: str, val, ttl: int = 60):
    try:
        json_val = json.dumps(val, cls=DateTimeEncoder)
        redis_client.setex(key, ttl, json_val)
    except Exception as e:
        log.warning(f"[cache] write error on {key}: {e}")

def delete_cache(key: str):
    try:
        redis_client.delete(key)
    except Exception as e:
        log.warning(f"[cache] delete error on {key}: {e}")

def delete_cache_prefix(prefix: str):
    try:
        cursor = 0
        pattern = f"{prefix}*"
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                redis_client.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        log.warning(f"[cache] prefix delete error on {prefix}: {e}")


def _resolve_public_ips(candidate_url: str):
    import urllib.parse
    import socket
    import ipaddress
    parsed = urllib.parse.urlparse(candidate_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname in {"localhost", "metadata.google.internal", "metadata.internal"}:
        raise ValueError("Blocked URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Could not resolve hostname")
        
    safe = []
    for info in resolved:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
            if not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
                if ip not in safe: safe.append(ip)
        except ValueError: continue
    if not safe: raise PermissionError("Blocked URL (Private/Reserved IP)")
    return safe

def _peer_ip(response):
    try:
        # 1. httpx support (preferred)
        # We look into the internal stream info which is the most reliable way 
        # to get the ACTUAL socket peer address after the connection is established.
        extensions = getattr(response, "extensions", {})
        stream = extensions.get("network_stream")
        if stream:
            addr = stream.get_extra_info("server_addr")
            if addr: return addr[0]
        
        # 2. requests support (fallback)
        raw = getattr(response, "raw", None)
        if raw is not None:
            # For urllib3/requests, we drill down into the low-level socket
            conn = getattr(raw, "connection", None) or getattr(raw, "_connection", None)
            if conn is not None:
                sock = getattr(conn, "sock", None)
                if sock is not None: return sock.getpeername()[0]
    except Exception: pass
    return None

def record_runtime_event(event: str, **fields):
    event = str(event or "").strip()
    if not event:
        return

    normalized_fields = {
        str(key): str(value)
        for key, value in fields.items()
        if value is not None and str(value) != ""
    }
    field_suffix = "|".join(
        f"{key}={normalized_fields[key]}"
        for key in sorted(normalized_fields)
    )
    bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    counter_key = f"presek:runtime_events:{bucket}"
    counter_field = event if not field_suffix else f"{event}|{field_suffix}"

    try:
        redis_client.hincrby(counter_key, counter_field, 1)
        redis_client.expire(counter_key, 60 * 60 * 24 * 14)
    except Exception as e:
        log.warning(f"[runtime_event] Redis unavailable for {counter_field}: {e}")

    if normalized_fields:
        log.info(f"[runtime_event] {event} {json.dumps(normalized_fields, ensure_ascii=False, sort_keys=True)}")
    else:
        log.info(f"[runtime_event] {event}")

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 60     # requests per window (general endpoints)
RATE_LIMIT_MAX_AI = 12  # requests per window (AI synthesis endpoints)
RATE_LIMIT_DAILY_AI = 100  # max AI calls per IP per day
AI_QUERY_MAX_LENGTH = 500  # max characters for AI query input


def _is_ai_analysis_path(path: str) -> bool:
    clean = str(path or "").strip()
    return clean.endswith("/research") or clean.endswith("/analyst")

def check_rate_limit(ip: str, path: str = "", is_authenticated: bool = False) -> bool:
    """Redis-backed rate limiter using a sliding window approach.
    Authenticated users get double the capacity."""
    # Exclude localhost from rate limiting to allow internal traffic (e.g. Astro SSR)
    if ip in {"127.0.0.1", "::1"}:
        return True

    # Determine limit tier
    max_requests = RATE_LIMIT_MAX
    scope = "general"
    daily_limit = None
    if _is_ai_analysis_path(path):
        scope = "ai"
        max_requests = RATE_LIMIT_MAX_AI
        daily_limit = RATE_LIMIT_DAILY_AI
    if is_authenticated:
        max_requests *= 2
        if daily_limit is not None:
            daily_limit *= 2

    tier = "auth" if is_authenticated else "anon"
    key = f"rate_limit:{tier}:{scope}:{ip}"
    now = time.time()

    try:
        if daily_limit is not None:
            bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
            daily_key = f"rate_limit_daily:{tier}:{scope}:{ip}:{bucket}"
            daily_count = redis_client.incr(daily_key)
            if daily_count == 1:
                redis_client.expire(daily_key, 60 * 60 * 24 * 2)
            if daily_count > daily_limit:
                return False

        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, RATE_LIMIT_WINDOW)

        results = pipe.execute()
        current_count = results[1]

        if current_count >= max_requests:
            return False

        return True
    except Exception as e:
        # Fail-open: Redis outage should not take down the site
        log.warning(f"[rate_limit] Redis unavailable for {ip}, allowing request: {e}")
        return True

def calculate_reading_time(text: str) -> int:
    """Estimates reading time in minutes (approx 200 wpm)."""
    if not text: return 1
    words = len(text.split())
    return max(1, math.ceil(words / 200))


def get_source_health_map(ttl_seconds: int = 60):
    now = time.time()
    if _SOURCE_STATUS_CACHE["data"] and now - _SOURCE_STATUS_CACHE["time"] < ttl_seconds:
        return _SOURCE_STATUS_CACHE["data"]
    try:
        raw = redis_client.hgetall("presek:source_statuses") or {}
        parsed = {key: json.loads(value) for key, value in raw.items()}
        _SOURCE_STATUS_CACHE["time"] = now
        _SOURCE_STATUS_CACHE["data"] = parsed
        return parsed
    except Exception as e:
        log.warning(f"[source_health] Redis unavailable, using static credibility only: {e}")
        return _SOURCE_STATUS_CACHE["data"] or {}


def get_source_quality_multiplier(source: str) -> float:
    status = get_source_health_map().get(source) or {}
    quality_score = status.get("quality_score")
    if quality_score is None:
        return 1.0
    try:
        quality_score = float(quality_score)
    except Exception:
        return 1.0
    return max(0.45, min(1.05, 0.55 + quality_score * 0.5))


def get_source_effective_weight(source: str) -> float:
    base = SOURCE_CREDIBILITY.get(source, DEFAULT_CREDIBILITY)
    mult = get_source_quality_multiplier(source)
    return base * mult


def get_source_trust_label(source: str) -> str:
    weight = get_source_effective_weight(source)
    if weight >= 1.75:
        return "Висока доверба"
    if weight >= 1.3:
        return "Потврден извор"
    return "Следен извор"


def _cluster_title_overlap(left: str, right: str) -> float:
    left_terms = {token for token in str(left or "").lower().split() if len(token) >= 4}
    right_terms = {token for token in str(right or "").lower().split() if len(token) >= 4}
    union = len(left_terms | right_terms) or 1
    return len(left_terms & right_terms) / union


def build_cluster_source_signals(arts):
    ranked = rank_articles_in_cluster(arts)
    if not ranked:
        return []

    lead = ranked[0]
    lead_title = str(lead.get("title") or "")
    lead_dt = _coerce_datetime(lead.get("created_at"))
    earliest_dt = min((_coerce_datetime(a.get("created_at")) for a in ranked if _coerce_datetime(a.get("created_at"))), default=None)
    corroboration_scores = []
    for article in ranked:
        title = str(article.get("title") or "")
        corroboration_scores.append(
            sum(
                1
                for other in ranked
                if other is not article and _cluster_title_overlap(title, str(other.get("title") or "")) >= 0.3
            )
        )

    signals = []
    for index, article in enumerate(ranked):
        source = str(article.get("source") or "")
        title = str(article.get("title") or "")
        effective_weight = get_source_effective_weight(source)
        category = SOURCE_CATEGORIES.get(source, "Локални")
        trust_label = get_source_trust_label(source)
        article_dt = _coerce_datetime(article.get("created_at"))
        overlap_with_lead = 1.0 if index == 0 else _cluster_title_overlap(title, lead_title)
        is_earliest = bool(article_dt and earliest_dt and article_dt <= earliest_dt)
        corroborated_by = corroboration_scores[index]

        if index == 0 and corroborated_by >= 2:
            role_label = "Примарен извор"
            role_note = "Овој извор ја носи главната линија што ја потврдуваат и повеќе други редакции."
            role_tone = "confirm"
        elif index == 0 and effective_weight >= 1.6:
            role_label = "Водечки доверлив извор"
            role_note = "Овој извор стои највисоко по доверба и ја дава најцелосната водечка рамка."
            role_tone = "lead"
        elif is_earliest and effective_weight >= 1.3:
            role_label = "Прв извештај"
            role_note = "Овој извор бил меѓу првите што го објавиле развојот."
            role_tone = "lead"
        elif overlap_with_lead < 0.22:
            role_label = "Различен агол"
            role_note = "Овој извор ја отвора приказната од друг аспект, а не само ја повторува водечката линија."
            role_tone = "contrast"
        elif article_dt and lead_dt and article_dt > lead_dt + datetime.timedelta(minutes=90):
            role_label = "Следење / реакција"
            role_note = "Овој извор доаѓа подоцна и повеќе носи реакција, последица или follow-up."
            role_tone = "context"
        else:
            role_label = "Дополнува контекст"
            role_note = "Овој извор ја потврдува главната приказна, но додава и свој контекст или детали."
            role_tone = "confirm" if overlap_with_lead >= 0.4 else "context"

        signals.append({
            "role_label": role_label,
            "role_note": role_note,
            "role_tone": role_tone,
            "trust_label": trust_label,
            "source_category": category,
            "effective_weight": round(effective_weight, 3),
            "corroborated_by": corroborated_by,
        })

    return signals


def annotate_cluster_articles(arts, prefer_recent=False):
    ranked = rank_articles_in_cluster(arts, prefer_recent=prefer_recent)
    signals = build_cluster_source_signals(ranked)
    
    # Media Pluralism Logic
    TIER_MAP = {
        "Агенциски": "M", "Јавен Сервис": "M", "Главни": "M",
        "Независни": "I", "Истражувачки": "I",
        "Регионални": "R", "Алтернативни": "R", "Локални": "R"
    }
    tiers_present = set()
    for art in ranked:
        src = art.get("source")
        cat = SOURCE_CATEGORIES.get(src, "Локални")
        tiers_present.add(TIER_MAP.get(cat, "R"))
    
    balance_score = len(tiers_present)
    if balance_score >= 3:
        balance_label = "Широк Консензус"
    elif balance_score == 2:
        balance_label = "Разновидни Извори"
    else:
        balance_label = None # Lean: don't show if one-sided unless many sources

    annotated = []
    for article, signal in zip(ranked, signals):
        enriched = dict(article)
        enriched["source_signal"] = signal
        # Add cluster-level balance signal to every article for easy access in frontend
        enriched["coverage_balance"] = {
            "score": balance_score,
            "label": balance_label
        }
        annotated.append(enriched)
    return annotated


def build_read_next_clusters(current_cluster_id, current_articles, current_tags, candidate_rows, limit=4):
    current_ranked = annotate_cluster_articles(current_articles or [])
    if not current_ranked:
        return []

    current_tags = {str(tag or "").strip() for tag in (current_tags or []) if str(tag or "").strip()}
    current_entities = {
        str(entity or "").strip()
        for article in current_ranked
        for entity in (article.get("entity_names") or [])
        if str(entity or "").strip()
    }
    current_topics = {
        str(article.get("topic") or "").strip()
        for article in current_ranked
        if str(article.get("topic") or "").strip()
    }
    current_lead_title = str(current_ranked[0].get("title") or "")

    grouped = {}
    for row in candidate_rows or []:
        cid = row.get("cluster_id")
        if not cid or cid == current_cluster_id:
            continue
        grouped.setdefault(cid, []).append(row)

    ranked_candidates = []
    for cid, rows in grouped.items():
        ranked = annotate_cluster_articles(rows)
        if not ranked:
            continue
        lead = ranked[0]
        candidate_tags = {
            str(tag or "").strip()
            for row in rows
            for tag in (row.get("cluster_tags") or [])
            if str(tag or "").strip()
        }
        candidate_entities = {
            str(entity or "").strip()
            for row in rows
            for entity in (row.get("entity_names") or [])
            if str(entity or "").strip()
        }
        candidate_topics = {
            str(row.get("topic") or "").strip()
            for row in rows
            if str(row.get("topic") or "").strip()
        }

        shared_tags = current_tags & candidate_tags
        shared_entities = current_entities & candidate_entities
        shared_topics = current_topics & candidate_topics
        title_overlap = _cluster_title_overlap(current_lead_title, str(lead.get("title") or ""))
        score = 0.0
        relation_label = "Ист контекст"
        relation_note = "Поврзан кластер што влегува во истиот поширок news cycle."

        if shared_entities and title_overlap >= 0.25:
            score += 2.0 + len(shared_entities) * 0.22
            relation_label = "Следен развој"
            relation_note = "Истите актери или тема, но со нов развој или следна фаза."
        elif shared_tags and title_overlap < 0.22:
            score += 1.6 + len(shared_tags) * 0.18
            relation_label = "Позадина и контекст"
            relation_note = "Поврзани информации и претходен контекст за оваа тема."
        elif shared_entities:
            score += 1.35 + len(shared_entities) * 0.15
            relation_label = "Исти актери, друг агол"
            relation_note = "Поврзани лица со оваа вест, но во поинаков контекст или настан."
        elif shared_topics:
            score += 1.05 + len(shared_topics) * 0.12

        if lead.get("source_signal", {}).get("trust_label") == "Висока доверба":
            score += 0.35
        if lead.get("source_signal", {}).get("role_label") in {"Најпотврден извор", "Водечки доверлив извор"}:
            score += 0.25

        recency_dt = _coerce_datetime(lead.get("created_at"))
        if recency_dt:
            hours_old = max(0.0, (datetime.datetime.now() - recency_dt).total_seconds() / 3600.0)
            score += max(0.0, 0.8 - min(0.8, hours_old * 0.08))

        if score <= 0.9:
            continue

        ranked_candidates.append({
            "cluster_id": cid,
            "title": lead.get("title"),
            "image_url": lead.get("image_url"),
            "relationship_label": relation_label,
            "relationship_note": relation_note,
            "shared_tags": sorted(shared_tags)[:3],
            "shared_entities": sorted(shared_entities)[:3],
            "shared_topics": sorted(shared_topics)[:2],
            "source": lead.get("source"),
            "created_at": lead.get("created_at"),
            "score": round(score, 3),
        })

    ranked_candidates.sort(key=lambda item: item["score"], reverse=True)
    return ranked_candidates[:limit]

def build_editor_analytics_payload(
    profile_stats_row=None,
    delivery_stats_row=None,
    top_topic_rows=None,
    top_source_rows=None,
    tracking_stats_row=None,
    tracking_performance_rows=None,
    suggestion_surface_rows=None,
    suggestion_kind_rows=None,
    suggestion_surface_period_rows=None,
):
    profile_stats_row = profile_stats_row or {}
    delivery_stats_row = delivery_stats_row or {}
    tracking_stats_row = tracking_stats_row or {}

    sends_7d = int(tracking_stats_row.get("sends_7d") or 0)
    opens_7d = int(tracking_stats_row.get("opens_7d") or 0)
    clicks_7d = int(tracking_stats_row.get("clicks_7d") or 0)
    delivery_kind_performance = []
    for row in tracking_performance_rows or []:
        delivery_kind = str(row.get("delivery_kind") or "").strip()
        if not delivery_kind:
            continue
        sends = int(row.get("sends") or 0)
        opens = int(row.get("opens") or 0)
        clicks = int(row.get("clicks") or 0)
        delivery_kind_performance.append({
            "delivery_kind": delivery_kind,
            "label": {
                "morning": "Утрински брифинг",
                "weekly": "Неделен дигест",
                "breaking": "Итно известување",
            }.get(delivery_kind, delivery_kind),
            "sends": sends,
            "opens": opens,
            "clicks": clicks,
            "open_rate": round((opens / sends) * 100, 1) if sends else 0.0,
            "click_rate": round((clicks / sends) * 100, 1) if sends else 0.0,
        })
    delivery_kind_performance.sort(
        key=lambda item: (
            item["click_rate"],
            item["open_rate"],
            item["sends"],
            item["label"],
        ),
        reverse=True,
    )

    suggestion_kind_performance = []
    for row in suggestion_kind_rows or []:
        suggestion_kind = str(row.get("suggestion_kind") or "").strip()
        if not suggestion_kind:
            continue
        impressions = int(row.get("impressions") or 0)
        follows = int(row.get("follows") or 0)
        dismissals = int(row.get("dismissals") or 0)
        suggestion_kind_performance.append({
            "suggestion_kind": suggestion_kind,
            "label": {
                "topic": "Теми",
                "source": "Извори",
            }.get(suggestion_kind, suggestion_kind),
            "impressions": impressions,
            "follows": follows,
            "dismissals": dismissals,
            "conversion_rate": round((follows / impressions) * 100, 1) if impressions else 0.0,
        })
    suggestion_kind_performance.sort(
        key=lambda item: (
            item["conversion_rate"],
            item["follows"],
            item["impressions"],
            item["label"],
        ),
        reverse=True,
    )

    suggestion_surface_performance = []
    suggestion_surface_period_map = {}
    for row in suggestion_surface_period_rows or []:
        surface = str(row.get("surface") or "").strip()
        if not surface:
            continue
        current_impressions = int(row.get("current_impressions") or 0)
        current_follows = int(row.get("current_follows") or 0)
        previous_impressions = int(row.get("previous_impressions") or 0)
        previous_follows = int(row.get("previous_follows") or 0)
        current_rate = round((current_follows / current_impressions) * 100, 1) if current_impressions else 0.0
        previous_rate = round((previous_follows / previous_impressions) * 100, 1) if previous_impressions else 0.0
        trend_delta = round(current_rate - previous_rate, 1)
        if trend_delta >= 3:
            trend_label = "Во раст"
        elif trend_delta <= -3:
            trend_label = "Во пад"
        else:
            trend_label = "Рамно"
        suggestion_surface_period_map[surface] = {
            "current_7d_impressions": current_impressions,
            "current_7d_follows": current_follows,
            "current_7d_rate": current_rate,
            "previous_7d_impressions": previous_impressions,
            "previous_7d_follows": previous_follows,
            "previous_7d_rate": previous_rate,
            "trend_delta": trend_delta,
            "trend_label": trend_label,
        }

    for row in suggestion_surface_rows or []:
        surface = str(row.get("surface") or "").strip()
        if not surface:
            continue
        impressions = int(row.get("impressions") or 0)
        follows = int(row.get("follows") or 0)
        dismissals = int(row.get("dismissals") or 0)
        topic_follows = int(row.get("topic_follows") or 0)
        source_follows = int(row.get("source_follows") or 0)
        suggestion_surface_performance.append({
            "surface": surface,
            "label": {
                "onboarding": "Почетен водич",
                "home_rail": "Почетна десна колона",
                "cluster": "Кластер страница",
                "topic": "Тема страница",
                "for_you": "За Вас",
                "settings": "Поставки",
            }.get(surface, surface),
            "impressions": impressions,
            "follows": follows,
            "dismissals": dismissals,
            "topic_follows": topic_follows,
            "source_follows": source_follows,
            "conversion_rate": round((follows / impressions) * 100, 1) if impressions else 0.0,
            **suggestion_surface_period_map.get(surface, {
                "current_7d_impressions": 0,
                "current_7d_follows": 0,
                "current_7d_rate": 0.0,
                "previous_7d_impressions": 0,
                "previous_7d_follows": 0,
                "previous_7d_rate": 0.0,
                "trend_delta": 0.0,
                "trend_label": "Рамно",
            }),
        })
    suggestion_surface_performance.sort(
        key=lambda item: (
            item["conversion_rate"],
            item["follows"],
            item["impressions"],
            item["label"],
        ),
        reverse=True,
    )

    return {
        "synced_profiles": int(profile_stats_row.get("synced_profiles") or 0),
        "active_profiles_7d": int(profile_stats_row.get("active_profiles_7d") or 0),
        "profiles_with_recent_reads": int(profile_stats_row.get("profiles_with_recent_reads") or 0),
        "profiles_following_topics": int(profile_stats_row.get("profiles_following_topics") or 0),
        "profiles_following_sources": int(profile_stats_row.get("profiles_following_sources") or 0),
        "delivery_active": int(delivery_stats_row.get("delivery_active") or 0),
        "delivery_targets": int(delivery_stats_row.get("delivery_targets") or 0),
        "morning_briefings": int(delivery_stats_row.get("morning_briefings") or 0),
        "weekly_digests": int(delivery_stats_row.get("weekly_digests") or 0),
        "breaking_topic_alerts": int(delivery_stats_row.get("breaking_topic_alerts") or 0),
        "breaking_source_alerts": int(delivery_stats_row.get("breaking_source_alerts") or 0),
        "sends_7d": sends_7d,
        "opens_7d": opens_7d,
        "clicks_7d": clicks_7d,
        "open_rate_7d": round((opens_7d / sends_7d) * 100, 1) if sends_7d else 0.0,
        "click_rate_7d": round((clicks_7d / sends_7d) * 100, 1) if sends_7d else 0.0,
        "delivery_kind_performance": delivery_kind_performance,
        "suggestion_surface_performance": suggestion_surface_performance,
        "suggestion_kind_performance": suggestion_kind_performance,
        "top_followed_topics": [
            {
                "topic": str(row.get("topic") or "").strip(),
                "followers": int(row.get("followers") or row.get("n") or 0),
            }
            for row in (top_topic_rows or [])
            if str(row.get("topic") or "").strip()
        ],
        "top_followed_sources": [
            {
                "source": str(row.get("source") or "").strip(),
                "followers": int(row.get("followers") or row.get("n") or 0),
            }
            for row in (top_source_rows or [])
            if str(row.get("source") or "").strip()
        ],
    }

def score_cluster(arts):
    """
    PageRank-style cluster importance score.
    Combines:
      - Source count (breadth of coverage)
      - Credibility-weighted source score
      - Recency (decays over 24h)
    """
    now = datetime.datetime.now()

    # Credibility score — sum of weights of unique sources
    unique_sources = {a["source"] for a in arts}
    cred_score = sum(
        get_source_effective_weight(s)
        for s in unique_sources
    )

    # Recency score — exponential decay, half-life = 6 hours
    try:
        ts = arts[0]["created_at"]
        if isinstance(ts, datetime.datetime):
            latest = ts.replace(tzinfo=None)
        else:
            latest = datetime.datetime.fromisoformat(ts.replace("+00:00", ""))
        hours_old = (now - latest).total_seconds() / 3600
    except Exception:
        hours_old = 24
    recency = math.exp(-0.115 * hours_old)  # e^(-ln2/6 * h) ≈ halves every 6h

    # Source count bonus (logarithmic — diminishing returns)
    breadth = math.log1p(len(arts))

    # Click engagement bonus
    total_clicks = sum(a.get("clicks", 0) or 0 for a in arts)
    click_bonus = 1 + math.log1p(total_clicks) * 0.15

    return cred_score * recency * breadth * click_bonus


def score_cluster_for_synthesis(arts):
    """
    Prioritization score for deciding which clusters deserve synthesis first.
    Compared to score_cluster(), this puts more weight on:
      - multi-source breadth and source diversity
      - likely disagreement / angle diversity across titles
      - user attention
      - the presence of enough context to produce a worthwhile synthesis
    """
    if not arts:
        return 0.0

    ranked = rank_articles_in_cluster(arts)
    base_score = score_cluster(ranked)
    unique_sources = {a.get("source") for a in ranked if a.get("source")}
    source_count = len(unique_sources)
    source_bonus = 1 + min(0.8, math.log1p(source_count) * 0.28)

    # More description text means the synthesizer has more evidence to work with.
    described_articles = sum(1 for a in ranked if str(a.get("description") or "").strip())
    context_bonus = 1 + min(0.35, described_articles * 0.08)

    # If titles diverge lexically, there is more likely angle diversity worth summarizing.
    title_terms = []
    for article in ranked[:6]:
        terms = {
            token
            for token in str(article.get("title") or "").lower().split()
            if len(token) >= 4
        }
        if terms:
            title_terms.append(terms)

    disagreement_bonus = 1.0
    if len(title_terms) >= 2:
        overlaps = []
        for idx in range(len(title_terms) - 1):
            left = title_terms[idx]
            right = title_terms[idx + 1]
            union = len(left | right) or 1
            overlaps.append(len(left & right) / union)
        if overlaps:
            avg_overlap = sum(overlaps) / len(overlaps)
            disagreement_bonus = 1 + max(0.0, min(0.28, (0.55 - avg_overlap) * 0.7))

    return base_score * source_bonus * context_bonus * disagreement_bonus


def score_cluster_for_homepage(arts):
    """
    Editorial homepage score.
    Rewards clusters that are fresh, corroborated, high-trust, and
    meaningfully developing across multiple sources.
    """
    if not arts:
        return 0.0

    ranked = rank_articles_in_cluster(arts)
    base_score = score_cluster(ranked)
    unique_sources = {a.get("source") for a in ranked if a.get("source")}
    source_count = len(unique_sources)
    signals = build_cluster_source_signals(ranked)

    avg_top_weight = 0.0
    if ranked:
        weights = [get_source_effective_weight(str(article.get("source") or "")) for article in ranked[:3]]
        avg_top_weight = sum(weights) / len(weights)
    trust_bonus = 1 + max(0.0, min(0.22, (avg_top_weight - 1.0) * 0.16))

    corroborated = sum(1 for signal in signals if signal.get("corroborated_by", 0) >= 1)
    corroboration_bonus = 1 + min(0.24, corroborated * 0.07)

    category_count = len({SOURCE_CATEGORIES.get(str(article.get("source") or ""), "Локални") for article in ranked if article.get("source")})
    breadth_bonus = 1 + min(0.2, max(0, source_count - 1) * 0.06) + min(0.08, max(0, category_count - 1) * 0.04)

    recent_cutoff = datetime.datetime.now() - datetime.timedelta(hours=6)
    recent_developments = sum(
        1
        for article in ranked
        if (_coerce_datetime(article.get("created_at")) or datetime.datetime.min) >= recent_cutoff
    )
    development_bonus = 1 + min(0.18, max(0, recent_developments - 1) * 0.06)

    thin_penalty = 1.0
    if source_count <= 1:
        thin_penalty *= 0.72
    elif source_count == 2 and not any(signal.get("corroborated_by", 0) >= 1 for signal in signals):
        thin_penalty *= 0.88

    description_count = sum(1 for article in ranked if str(article.get("description") or "").strip())
    if description_count <= 1 and source_count <= 2:
        thin_penalty *= 0.9

    return base_score * trust_bonus * corroboration_bonus * breadth_bonus * development_bonus * thin_penalty


def _coerce_datetime(value):
    if isinstance(value, datetime.datetime):
        # Normalize to UTC for consistent comparisons across the app
        if value.tzinfo is not None:
            return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value
    if not value:
        return None
    try:
        # 1. Try standard ISO format (handles offsets like +02:00 correctly in Python 3.7+)
        s = str(value).replace(" ", "T")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        try:
            # 2. Fallback: manually strip offset ONLY if fromisoformat failed
            import re
            m = re.match(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", str(value))
            if m: return datetime.datetime.fromisoformat(m.group(1).replace(" ", "T"))
            return None
        except:
            return None


def _number_tokens(text: str) -> set[str]:
    import re
    return set(re.findall(r"\b\d+(?::\d+)?(?:[%.,]\d+)?\b", str(text or "")))


def _title_overlap(left: str, right: str) -> float:
    left_terms = {token for token in str(left or "").lower().split() if len(token) >= 4}
    right_terms = {token for token in str(right or "").lower().split() if len(token) >= 4}
    union = len(left_terms | right_terms) or 1
    return len(left_terms & right_terms) / union


def assess_cluster_synthesis_freshness(arts, synthesis_created_at):
    """
    Decide whether an existing synthesis should be refreshed based on
    meaningful cluster changes after the last synthesis time.
    """
    if not arts:
        return {
            "has_synthesis": bool(synthesis_created_at),
            "refresh_needed": False,
            "is_stale": False,
            "freshness_score": 0.0,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": None,
            "synthesis_updated_at": _coerce_datetime(synthesis_created_at),
        }

    ranked = rank_articles_in_cluster(arts)
    synthesis_dt = _coerce_datetime(synthesis_created_at)
    latest_article_at = max((_coerce_datetime(a.get("created_at")) for a in ranked), default=None)

    if not synthesis_dt:
        return {
            "has_synthesis": False,
            "refresh_needed": True,
            "is_stale": False,
            "freshness_score": 10.0,
            "reasons": ["missing_synthesis"],
            "new_article_count": len(ranked),
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": None,
        }

    newer_articles = []
    older_articles = []
    for article in ranked:
        article_dt = _coerce_datetime(article.get("created_at"))
        if article_dt and article_dt > synthesis_dt:
            newer_articles.append(article)
        else:
            older_articles.append(article)

    if not newer_articles:
        return {
            "has_synthesis": True,
            "refresh_needed": False,
            "is_stale": False,
            "freshness_score": 0.0,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": synthesis_dt,
        }

    score = 0.0
    reasons = []

    newer_sources = {a.get("source") for a in newer_articles if a.get("source")}
    older_sources = {a.get("source") for a in older_articles if a.get("source")}
    net_new_sources = sorted(source for source in newer_sources if source not in older_sources)
    if (net_new_sources):
        # Significant bonus for new voices
        score += min(2.0, 1.0 + len(net_new_sources) * 0.4)
        reasons.append("new_sources")

    newer_numbers = set()
    older_numbers = set()
    for article in newer_articles:
        newer_numbers |= _number_tokens(" ".join([str(article.get("title") or ""), str(article.get("description") or "")]))
    for article in older_articles:
        older_numbers |= _number_tokens(" ".join([str(article.get("title") or ""), str(article.get("description") or "")]))
    if (newer_numbers - older_numbers):
        score += 1.1
        reasons.append("new_numbers")

    if older_articles:
        newest_title = str(newer_articles[0].get("title") or "")
        baseline_title = str(older_articles[0].get("title") or "")
        if newest_title and baseline_title and _title_overlap(newest_title, baseline_title) < 0.26:
            score += 0.9
            reasons.append("new_angle")

    if len(newer_articles) >= 2:
        score += 0.5
        reasons.append("multiple_new_reports")

    high_weight_new_source = any(get_source_effective_weight(str(article.get("source") or "")) >= 1.45 for article in newer_articles)
    if high_weight_new_source:
        score += 0.65
        reasons.append("credible_new_reporting")

    current_score = score_cluster_for_synthesis(ranked)
    if current_score >= 3.5:
        score += 0.5
        reasons.append("high_priority_cluster")

    # Diversity bonus: if the cluster is becoming "balanced" (multi-source types)
    if is_balanced(ranked) and not is_balanced(older_articles):
        score += 1.2
        reasons.append("broad_coverage_achieved")

    age_minutes = max(0.0, ((latest_article_at or synthesis_dt) - synthesis_dt).total_seconds() / 60.0)
    
    # Dynamic cooldown: shorter for high-priority or very fresh breaking news
    min_cooldown = 40 if current_score < 4.0 else 20
    cooldown_active = age_minutes < min_cooldown and (len(newer_articles) < 2 and not net_new_sources)
    
    # Refresh if score is substantial (2.0+) or many new articles
    # Increased threshold slightly to avoid "nervous" updates on minor changes
    refresh_needed = (score >= 2.0 or len(newer_articles) >= 4) and not cooldown_active

    return {
        "has_synthesis": True,
        "refresh_needed": refresh_needed,
        "is_stale": refresh_needed,
        "freshness_score": round(score, 3),
        "reasons": reasons,
        "new_article_count": len(newer_articles),
        "latest_article_at": latest_article_at,
        "synthesis_updated_at": synthesis_dt,
    }


def rank_articles_in_cluster(arts, prefer_recent=False):
    """Within a cluster, put the most credible source first and mark near-duplicates."""
    if not arts: return []
    
    # Sort by raw weight first to find the "best" representative for each near-duplicate group
    def initial_weight(article):
        source_weight = get_source_effective_weight(article["source"])
        description_text = str(article.get("description") or "").strip()
        description_bonus = 0.12 if description_text else 0.0
        
        # If we prefer recent (Live mode), the lead SHOULD be the latest development
        if prefer_recent:
            created_at = _coerce_datetime(article.get("created_at")) or datetime.datetime.min
            # Use timestamp directly as the base, weight as a tiny tie-breaker
            return created_at.timestamp() + (source_weight * 0.001)
            
        return source_weight + description_bonus

    sorted_arts = sorted(arts, key=initial_weight, reverse=True)
    ranked = []
    seen_norm_titles = [] # List of (representative_title, [member_indices])

    for i, article in enumerate(sorted_arts):
        title = str(article.get("title") or "").strip()
        is_redundant = False
        
        # Check if this title is a near-duplicate of something we already ranked
        for rep_title in seen_norm_titles:
            if _cluster_title_overlap(title, rep_title) >= 0.85:
                is_redundant = True
                break
        
        enriched = dict(article)
        enriched["is_redundant"] = is_redundant
        ranked.append(enriched)
        
        if not is_redundant:
            seen_norm_titles.append(title)

    # Final sort to ensure non-redundant and high-weight ones are at the top
    def final_sort_key(article):
        # penalize redundancy heavily in sorting
        redundancy_penalty = -5.0 if article.get("is_redundant") else 0.0
        source_weight = get_source_effective_weight(article["source"])
        created_at = _coerce_datetime(article.get("created_at")) or datetime.datetime.min
        
        if prefer_recent:
            # recency first, then weight
            return (redundancy_penalty, created_at, source_weight)
            
        return (redundancy_penalty + source_weight, created_at)

    return sorted(ranked, key=final_sort_key, reverse=True)

def is_balanced(arts) -> bool:
    """True if cluster contains 3+ unique sources from different categories."""
    from config import SOURCE_CATEGORIES, BALANCED_COVERAGE_THRESHOLD
    if len(arts) < BALANCED_COVERAGE_THRESHOLD:
        return False
    
    unique_categories = {SOURCE_CATEGORIES.get(a["source"], "Локални") for a in arts}
    unique_sources = {a["source"] for a in arts}
    
    # Balanced if 3+ sources OR 2+ distinct categories (e.g. Mainstream + Independent)
    return len(unique_sources) >= 4 or len(unique_categories) >= 2

def publish_event(channel: str, data: dict):
    """Broadcast a JSON message to a Redis channel."""
    try:
        redis_client.publish(channel, json.dumps(data, cls=DateTimeEncoder))
    except Exception as e:
        log.warning(f"[pubsub] publish error on {channel}: {e}")

async def event_stream(channel: str, request=None):
    """Async generator for SSE that exits cleanly on disconnect or shutdown."""
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)
    last_keepalive = time.monotonic()
    yield "retry: 10000\n\n"
    try:
        while True:
            if request is not None and await request.is_disconnected():
                break

            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                data = message["data"]
                yield f"data: {data}\n\n"
                last_keepalive = time.monotonic()
                continue

            if time.monotonic() - last_keepalive >= 15:
                yield ": keepalive\n\n"
                last_keepalive = time.monotonic()

            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        log.info(f"[pubsub] stream cancelled on {channel}")
        raise
    except Exception as e:
        log.error(f"[pubsub] stream error on {channel}: {e}")
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()

def build_source_reputation_rows(source_rows, pulse_rows=None, speed_rows=None, history_rows=None, category_rows=None):
    pulse_map = {
        str(item.get("source") or ""): int(item.get("count") or item.get("n") or 0)
        for item in (pulse_rows or [])
    }
    speed_map = {
        str(item.get("source") or ""): int(item.get("first_count") or 0)
        for item in (speed_rows or [])
    }
    history_map = {
        str(item.get("source") or ""): {
            "lead_count_30d": int(item.get("lead_count_30d") or 0),
            "corroborated_lead_count_30d": int(item.get("corroborated_lead_count_30d") or 0),
            "solo_lead_count_30d": int(item.get("solo_lead_count_30d") or 0),
            "recent_7d_volume": int(item.get("recent_7d_volume") or 0),
            "previous_7d_volume": int(item.get("previous_7d_volume") or 0),
        }
        for item in (history_rows or [])
    }
    
    # Process category dominance
    from collections import defaultdict
    category_map = defaultdict(list)
    for crow in (category_rows or []):
        src = str(crow.get("source") or "")
        if src and len(category_map[src]) < 3:
            category_map[src].append(crow["category"])

    results = []
    for row in source_rows or []:
        name = str(row.get("name") or row.get("source") or "").strip()
        if not name:
            continue
        credibility = float(row.get("credibility") or SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY))
        effective_weight = get_source_effective_weight(name)
        recent_volume = pulse_map.get(name, 0)
        speed_count = speed_map.get(name, 0)
        history = history_map.get(name, {})
        lead_count_30d = int(history.get("lead_count_30d") or 0)
        corroborated_lead_count_30d = int(history.get("corroborated_lead_count_30d") or 0)
        solo_lead_count_30d = int(history.get("solo_lead_count_30d") or 0)
        recent_7d_volume = int(history.get("recent_7d_volume") or 0)
        previous_7d_volume = int(history.get("previous_7d_volume") or 0)
        
        corroboration_rate = (
            round(corroborated_lead_count_30d / lead_count_30d, 2)
            if lead_count_30d > 0
            else 0.0
        )
        lone_lead_rate = (
            round(solo_lead_count_30d / lead_count_30d, 2)
            if lead_count_30d > 0
            else 0.0
        )
        trend_delta = recent_7d_volume - previous_7d_volume

        if trend_delta >= 4:
            trend_label = "Расте"
        elif trend_delta <= -4:
            trend_label = "Слабее"
        else:
            trend_label = "Стабилен ритам"

        if effective_weight >= 1.75:
            tier = "Висока доверба"
        elif effective_weight >= 1.3:
            tier = "Потврден извор"
        else:
            tier = "Следен извор"

        if speed_count >= 10:
            tendency = "Често прв на приказната"
        elif corroboration_rate >= 0.7 and lead_count_30d >= 4:
            tendency = "Често води и подоцна се потврдува"
        elif lone_lead_rate >= 0.55 and lead_count_30d >= 4:
            tendency = "Често води сам без брза потврда"
        elif recent_volume >= 8:
            tendency = "Силен дневен ритам"
        elif recent_volume >= 3:
            tendency = "Постојано присуство"
        else:
            tendency = "Поретки, но следени објави"

        results.append({
            "source": name,
            "country": row.get("country") or "",
            "category": row.get("category") or "",
            "top_categories": category_map.get(name, []),
            "credibility": round(credibility, 2),
            "effective_weight": round(effective_weight, 2),
            "trust_tier": tier,
            "recent_volume": recent_volume,
            "speed_first_count": speed_count,
            "corroboration_rate": corroboration_rate,
            "lone_lead_rate": lone_lead_rate,
            "lead_count_30d": lead_count_30d,
            "tendency": tendency,
            "trend_label": trend_label,
            "trend_delta": trend_delta,
            "last_fetched": row.get("last_fetched"),
            "paused_at": row.get("paused_at"),
            "is_active": row.get("is_active", True)
        })

    results.sort(
        key=lambda item: (
            item["effective_weight"],
            item["recent_volume"],
            item["speed_first_count"],
            item["source"].lower(),
        ),
        reverse=True,
    )
    return results
