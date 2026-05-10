import datetime
import asyncio
import logging
import math
import redis
import json
import os
import time
import re
import socket
import ipaddress
import urllib.parse
from PIL import Image
from io import BytesIO
from typing import Optional, List, Dict, Any
from config import (
    SOURCE_CREDIBILITY,
    DEFAULT_CREDIBILITY,
    SOURCE_CATEGORIES,
    BALANCED_COVERAGE_THRESHOLD,
)

log = logging.getLogger("presek")

# Redis client with password support
# REDIS_URL format: redis://[:password@]hostname[:port]/db
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    # Test connection
    redis_client.ping()
    log.info(f"Redis connected: {redis_url.split('@')[-1].split('/')[0]}")
except redis.ConnectionError as e:
    log.error(f"Redis connection failed to {redis_url}: {e}")
    # Fallback to localhost without password for backward compatibility
    redis_client = redis.Redis.from_url(
        "redis://localhost:6379/0", decode_responses=True
    )
except Exception as e:
    log.error(f"Redis initialization error: {e}")
    # Last resort: create a client that will fail on first use
    redis_client = redis.Redis.from_url(
        "redis://localhost:6379/0", decode_responses=True
    )

_SOURCE_STATUS_CACHE = {"time": 0.0, "data": {}}
_SOURCE_REGISTRY_CACHE = {"time": 0.0, "data": {}}


def get_source_registry(ttl_seconds: int = 300) -> Dict[str, Dict[str, Any]]:
    """
    Returns a unified map of source metadata (credibility, category).
    Prefer database values, fall back to hardcoded config.
    """
    now = time.time()
    if (
        _SOURCE_REGISTRY_CACHE["data"]
        and now - _SOURCE_REGISTRY_CACHE["time"] < ttl_seconds
    ):
        return _SOURCE_REGISTRY_CACHE["data"]

    # Initialize with hardcoded defaults
    registry = {}

    # We use a combined set of keys from hardcoded and DB
    all_names = set(SOURCE_CREDIBILITY.keys()) | set(SOURCE_CATEGORIES.keys())

    for name in all_names:
        registry[name] = {
            "name": name,
            "credibility": float(SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY)),
            "category": SOURCE_CATEGORIES.get(name, "Локални"),
        }

    # Override/Extend with database values
    try:
        from database import db_manager as db

        # We perform a raw query to avoid complex model overhead during config loading
        rows = db.execute(
            "SELECT name, credibility, category FROM sources WHERE is_active = TRUE"
        )
        for row in rows:
            name = row["name"] if isinstance(row, dict) else row[0]
            cred = row["credibility"] if isinstance(row, dict) else row[1]
            cat = row["category"] if isinstance(row, dict) else row[2]

            registry[name] = {
                "name": name,
                "credibility": float(
                    cred
                    if cred is not None
                    else SOURCE_CREDIBILITY.get(name, DEFAULT_CREDIBILITY)
                ),
                "category": cat or SOURCE_CATEGORIES.get(name, "Локални"),
            }
    except Exception as e:
        log.warning(
            f"[source_registry] Database metadata unavailable, using hardcoded only: {e}"
        )

    _SOURCE_REGISTRY_CACHE["time"] = now
    _SOURCE_REGISTRY_CACHE["data"] = registry
    return registry


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects."""

    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            if isinstance(obj, datetime.datetime) and obj.tzinfo is None:
                return obj.isoformat() + "Z"
            return obj.isoformat()
        return super().default(obj)


async def get_dominant_color(url: str) -> str:
    """Extracts the dominant hex color from an image URL (Asynchronous)."""
    if not url:
        return ""

    internal_proxy_markers = [
        "/api/proxy",
        "presek.live/proxy",
        "localhost:5001/proxy",
        "api:5001/proxy",
    ]
    if any(marker in url for marker in internal_proxy_markers):
        log.warning(
            f"[utils] color extraction blocked for recursive/internal URL: {url}"
        )
        return ""

    if not url.startswith("http"):
        return ""

    try:
        import httpx

        try:
            import pillow_avif  # noqa: F401
        except ImportError:
            pass

        async with httpx.AsyncClient(
            timeout=4.0, follow_redirects=True, max_redirects=2
        ) as client:
            try:
                safe_ips = _resolve_public_ips(url)
            except Exception:
                return ""

            async with client.stream(
                "GET", url, headers={"User-Agent": "PresekColorBot/1.0"}
            ) as response:
                if response.status_code != 200:
                    return ""

                p_ip = _peer_ip(response)
                if not p_ip or p_ip not in safe_ips:
                    log.warning(
                        f"[utils] color extraction blocked: IP mismatch/private for {url}"
                    )
                    return ""

                content = await response.aread()

        img = Image.open(BytesIO(content))
        img = img.convert("RGB")
        img.thumbnail((60, 60))

        colors = img.getcolors(3600)
        if not colors:
            return ""

        def is_usable(rgb):
            r, g, b = rgb
            if r > 245 and g > 245 and b > 245:
                return False
            if r < 15 and g < 15 and b < 15:
                return False
            avg = (r + g + b) / 3
            if abs(r - avg) < 12 and abs(g - avg) < 12 and abs(b - avg) < 12:
                return False
            return True

        sorted_colors = sorted(colors, key=lambda x: x[0], reverse=True)
        usable = [c for c in sorted_colors if is_usable(c[1])]
        dominant = usable[0][1] if usable else sorted_colors[0][1]

        return "#{:02x}{:02x}{:02x}".format(*dominant)
    except Exception as e:
        log.debug(f"[utils] color extraction failed for {url}: {e}")
        return ""


def cached_response(key: str, ttl: int = 60) -> Optional[Any]:
    """Read a cached JSON value from Redis."""
    try:
        val = redis_client.get(key)
        if val:
            return json.loads(val)
    except Exception as e:
        log.warning(f"[cache] redis read error on {key}: {e}")
    return None


def set_cache(key: str, val, ttl: int = 60):
    """Write a JSON value to Redis cache."""
    try:
        json_val = json.dumps(val, cls=DateTimeEncoder)
        redis_client.setex(key, ttl, json_val)
    except Exception as e:
        log.warning(f"[cache] write error on {key}: {e}")


def delete_cache(key: str):
    """Delete a key from Redis cache."""
    try:
        redis_client.delete(key)
    except Exception as e:
        log.warning(f"[cache] delete error on {key}: {e}")


def delete_cache_prefix(prefix: str):
    """Delete all keys with a given prefix from Redis."""
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


def format_sources(count: int) -> str:
    """Pluralization helper for Macedonian sources."""
    if count == 1:
        return "1 извор"
    elif 2 <= count <= 4:
        return f"{count} извора"
    return f"{count} извори"


def _resolve_public_ips(candidate_url: str) -> List[str]:
    parsed = urllib.parse.urlparse(candidate_url)
    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname in {
        "localhost",
        "metadata.google.internal",
        "metadata.internal",
    }:
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
            if not (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
                or addr.is_unspecified
            ):
                if ip not in safe:
                    safe.append(ip)
        except ValueError:
            continue
    if not safe:
        raise PermissionError("Blocked URL (Private/Reserved IP)")
    return safe


def _peer_ip(response) -> Optional[str]:
    try:
        # httpx support
        extensions = getattr(response, "extensions", {})
        stream = extensions.get("network_stream")
        if stream:
            addr = stream.get_extra_info("server_addr")
            if addr:
                return addr[0]

        # requests support
        raw = getattr(response, "raw", None)
        if raw is not None:
            conn = getattr(raw, "connection", None) or getattr(raw, "_connection", None)
            if conn is not None:
                sock = getattr(conn, "sock", None)
                if sock is not None:
                    return sock.getpeername()[0]
    except Exception:
        pass
    return None


def record_runtime_event(event: str, **fields):
    """Record an application event to Redis for analytics."""
    event = str(event or "").strip()
    if not event:
        return

    normalized_fields = {
        str(k): str(v) for k, v in fields.items() if v is not None and str(v) != ""
    }
    field_suffix = "|".join(
        f"{k}={normalized_fields[k]}" for k in sorted(normalized_fields)
    )
    bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    counter_key = f"presek:runtime_events:{bucket}"
    counter_field = event if not field_suffix else f"{event}|{field_suffix}"

    try:
        redis_client.hincrby(counter_key, counter_field, 1)
        redis_client.expire(counter_key, 60 * 60 * 24 * 14)
    except Exception as e:
        log.warning(f"[runtime_event] Redis unavailable: {e}")

    log.info(
        f"[runtime_event] {event} {json.dumps(normalized_fields, ensure_ascii=False)}"
    )


def check_rate_limit(ip: str, path: str = "", is_authenticated: bool = False) -> bool:
    """Sliding window rate limiter."""
    if ip in {"127.0.0.1", "::1"}:
        return True

    is_ai = path.endswith("/research") or path.endswith("/analyst")
    max_reqs = 12 if is_ai else 60
    daily_lim = 100 if is_ai else None

    if is_authenticated:
        max_reqs *= 2
        if daily_lim:
            daily_lim *= 2

    tier = "auth" if is_authenticated else "anon"
    scope = "ai" if is_ai else "general"
    key = f"rate_limit:{tier}:{scope}:{ip}"
    now = time.time()

    try:
        if daily_lim:
            bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
            daily_key = f"rate_limit_daily:{tier}:{scope}:{ip}:{bucket}"
            if redis_client.incr(daily_key) > daily_lim:
                return False
            redis_client.expire(daily_key, 172800)

        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, now - 60)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, 60)
        results = pipe.execute()
        return results[1] < max_reqs
    except Exception:
        return True


def calculate_reading_time(text: str) -> int:
    """Estimates reading time in minutes."""
    if not text:
        return 1
    return max(1, math.ceil(len(text.split()) / 200))


def get_source_health_map(ttl: int = 60) -> Dict[str, Any]:
    now = time.time()
    if _SOURCE_STATUS_CACHE["data"] and now - _SOURCE_STATUS_CACHE["time"] < ttl:
        return _SOURCE_STATUS_CACHE["data"]
    try:
        raw = redis_client.hgetall("presek:source_statuses") or {}
        parsed = {k: json.loads(v) for k, v in raw.items()}
        _SOURCE_STATUS_CACHE.update({"time": now, "data": parsed})
        return parsed
    except Exception:
        return _SOURCE_STATUS_CACHE["data"] or {}


def get_source_quality_multiplier(source: str) -> float:
    status = get_source_health_map().get(source) or {}
    q_score = status.get("quality_score")
    if q_score is None:
        return 1.0
    return max(0.45, min(1.05, 0.55 + float(q_score) * 0.5))


def get_source_effective_weight(source: str) -> float:
    reg = get_source_registry()
    base = reg.get(source, {}).get("credibility", DEFAULT_CREDIBILITY)
    return base * get_source_quality_multiplier(source)


def get_source_trust_label(source: str) -> str:
    weight = get_source_effective_weight(source)
    if weight >= 1.75:
        return "Висока доверба"
    if weight >= 1.3:
        return "Потврден извор"
    return "Следен извор"


def _coerce_datetime(value) -> Optional[datetime.datetime]:
    if isinstance(value, datetime.datetime):
        if value.tzinfo:
            return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return value
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace(" ", "T"))
        if dt.tzinfo:
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        m = re.match(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", str(value))
        if m:
            return datetime.datetime.fromisoformat(m.group(1).replace(" ", "T"))
    return None


def _cluster_title_overlap(left: str, right: str) -> float:
    l_set = {t for t in str(left or "").lower().split() if len(t) >= 4}
    r_set = {t for t in str(right or "").lower().split() if len(t) >= 4}
    union = len(l_set | r_set) or 1
    return len(l_set & r_set) / union


def build_cluster_source_signals(arts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ranked = rank_articles_in_cluster(arts)
    if not ranked:
        return []

    lead_title = str(ranked[0].get("title") or "")
    lead_dt = _coerce_datetime(ranked[0].get("created_at"))
    earliest_dt = min(
        (
            _coerce_datetime(a.get("created_at"))
            for a in ranked
            if _coerce_datetime(a.get("created_at"))
        ),
        default=None,
    )

    corrob_scores = []
    for art in ranked:
        t = str(art.get("title") or "")
        corrob_scores.append(
            sum(
                1
                for o in ranked
                if o is not art
                and _cluster_title_overlap(t, str(o.get("title") or "")) >= 0.3
            )
        )

    signals = []
    reg = get_source_registry()
    for idx, art in enumerate(ranked):
        src = str(art.get("source") or "")
        weight = get_source_effective_weight(src)
        art_dt = _coerce_datetime(art.get("created_at"))
        overlap = (
            1.0
            if idx == 0
            else _cluster_title_overlap(str(art.get("title") or ""), lead_title)
        )
        corrob_by = corrob_scores[idx]

        if idx == 0 and corrob_by >= 2:
            role, note, tone = (
                "Најпотврден извор",
                "Овој извор ја носи главната линија што ја потврдуваат и повеќе други редакции.",
                "confirm",
            )
        elif idx == 0 and weight >= 1.6:
            role, note, tone = (
                "Водечки доверлив извор",
                "Овој извор стои највисоко по доверба и ја дава најцелосната водечка рамка.",
                "lead",
            )
        elif art_dt and earliest_dt and art_dt <= earliest_dt and weight >= 1.3:
            role, note, tone = (
                "Прв извештај",
                "Овој извор бил меѓу првите што го објавиле развојот.",
                "lead",
            )
        elif overlap < 0.22:
            role, note, tone = (
                "Различен агол",
                "Овој извор ја отвора приказната од друг аспект, а не само ја повторува водечката линија.",
                "contrast",
            )
        elif art_dt and lead_dt and art_dt > lead_dt + datetime.timedelta(minutes=90):
            role, note, tone = (
                "Следење / реакција",
                "Овој извор доаѓа подоцна и повеќе носи реакција, последица или follow-up.",
                "context",
            )
        else:
            role, note, tone = (
                "Дополнува контекст",
                "Овој извор ја потврдува главната приказна, но додава и свој контекст или детали.",
                "confirm" if overlap >= 0.4 else "context",
            )

        signals.append(
            {
                "role_label": role,
                "role_note": note,
                "role_tone": tone,
                "trust_label": get_source_trust_label(src),
                "source_category": reg.get(src, {}).get("category", "Локални"),
                "effective_weight": round(weight, 3),
                "corroborated_by": corrob_by,
            }
        )
    return signals


def annotate_cluster_articles(
    arts: List[Dict[str, Any]], prefer_recent: bool = False
) -> List[Dict[str, Any]]:
    ranked = rank_articles_in_cluster(arts, prefer_recent=prefer_recent)
    signals = build_cluster_source_signals(ranked)

    TIER_MAP = {
        "Агенциски": "M",
        "Јавен Сервис": "M",
        "Главни": "M",
        "Независни": "I",
        "Истражувачки": "I",
        "Регионални": "R",
        "Алтернативни": "R",
        "Локални": "R",
    }
    reg = get_source_registry()
    tiers = {
        TIER_MAP.get(reg.get(a["source"], {}).get("category", "Локални"), "R")
        for a in ranked
    }

    bal_score = len(tiers)
    bal_label = (
        "Широк Консензус"
        if bal_score >= 3
        else ("Разновидни Извори" if bal_score == 2 else None)
    )

    annotated = []
    lead = ranked[0] if ranked else None
    for idx, (art, sig) in enumerate(zip(ranked, signals)):
        enriched = {
            **art,
            "source_signal": sig,
            "coverage_balance": {"score": bal_score, "label": bal_label},
        }
        if idx == 0:
            enriched["relationship_to_lead"] = {
                "tone": "lead",
                "label": "ОСНОВНА ОБЈАВА",
            }
        else:
            overlap = _cluster_title_overlap(
                lead.get("title", ""), art.get("title", "")
            )
            label = (
                "ИСТА ПРИКАЗНА"
                if overlap >= 0.45
                else ("ПОВРЗАНА ПРИКАЗНА" if overlap >= 0.20 else "ИСТ КОНТЕКСТ")
            )
            enriched["relationship_to_lead"] = {"tone": "neutral", "label": label}
        annotated.append(enriched)
    return annotated


def rank_articles_in_cluster(
    arts: List[Dict[str, Any]], prefer_recent: bool = False
) -> List[Dict[str, Any]]:
    if not arts:
        return []

    def initial_weight(a):
        w = get_source_effective_weight(a["source"]) + (
            0.12 if str(a.get("description") or "").strip() else 0.0
        )
        if prefer_recent:
            return (
                _coerce_datetime(a.get("created_at")) or datetime.datetime.min
            ).timestamp() + (w * 0.001)
        return w

    sorted_arts = sorted(arts, key=initial_weight, reverse=True)
    ranked = []
    seen_titles = []
    for art in sorted_arts:
        t = str(art.get("title") or "").strip()
        is_red = any(_cluster_title_overlap(t, prev) >= 0.85 for prev in seen_titles)
        ranked.append({**art, "is_redundant": is_red})
        if not is_red:
            seen_titles.append(t)

    def final_key(a):
        penalty = -5.0 if a.get("is_redundant") else 0.0
        w = get_source_effective_weight(a["source"])
        dt = _coerce_datetime(a.get("created_at")) or datetime.datetime.min
        return (penalty, dt, w) if prefer_recent else (penalty + w, dt)

    return sorted(ranked, key=final_key, reverse=True)


def build_read_next_clusters(
    cur_id: str,
    cur_arts: List[Dict[str, Any]],
    cur_tags: List[str],
    candidates: List[Dict[str, Any]],
    limit: int = 4,
) -> List[Dict[str, Any]]:
    cur_ranked = annotate_cluster_articles(cur_arts or [])
    if not cur_ranked:
        return []

    c_tags = {str(t).strip() for t in (cur_tags or []) if str(t).strip()}
    c_ents = {
        str(e).strip()
        for a in cur_ranked
        for e in (a.get("entity_names") or [])
        if str(e).strip()
    }
    c_topics = {
        str(a.get("topic")).strip() for a in cur_ranked if str(a.get("topic")).strip()
    }
    c_lead_title = str(cur_ranked[0].get("title") or "")

    grouped = {}
    for r in candidates or []:
        cid = r.get("cluster_id")
        if cid and cid != cur_id:
            grouped.setdefault(cid, []).append(r)

    results = []
    for cid, rows in grouped.items():
        ranked = annotate_cluster_articles(rows)
        if not ranked:
            continue
        lead = ranked[0]
        cand_tags = {
            str(t).strip()
            for r in rows
            for t in (r.get("cluster_tags") or [])
            if str(t).strip()
        }
        cand_ents = {
            str(e).strip()
            for r in rows
            for e in (r.get("entity_names") or [])
            if str(e).strip()
        }
        cand_topics = {
            str(r.get("topic")).strip() for r in rows if str(r.get("topic")).strip()
        }

        sh_tags, sh_ents, sh_topics = (
            c_tags & cand_tags,
            c_ents & cand_ents,
            c_topics & cand_topics,
        )
        overlap = _cluster_title_overlap(c_lead_title, str(lead.get("title") or ""))

        score = 0.0
        label, note = "Ист контекст", "Поврзан кластер со сличен новинарски контекст."

        if sh_ents and overlap >= 0.25:
            score += 2.0 + len(sh_ents) * 0.22
            label, note = (
                "Следен развој",
                "Истите актери или тема, но со нов развој или следна фаза.",
            )
        elif sh_tags and overlap < 0.22:
            score += 1.6 + len(sh_tags) * 0.18
            label, note = "Позадина и контекст", "Ја шири сликата со поврзан контекст."
        elif sh_ents:
            score += 1.35 + len(sh_ents) * 0.15
            label, note = (
                "Исти актери, друг агол",
                "Ги врзува истите имиња, но од поинаков агол.",
            )
        elif sh_topics:
            score += 1.05 + len(sh_topics) * 0.12
        else:
            continue

        if lead.get("source_signal", {}).get("trust_label") == "Висока доверба":
            score += 0.35
        dt = _coerce_datetime(lead.get("created_at"))
        if dt:
            score += max(
                0.0,
                0.8
                - min(
                    0.8, (datetime.datetime.now() - dt).total_seconds() / 3600.0 * 0.08
                ),
            )

        if score > 0.9:
            results.append(
                {
                    "cluster_id": cid,
                    "title": lead.get("title"),
                    "image_url": lead.get("image_url"),
                    "relationship_label": label,
                    "relationship_note": note,
                    "shared_tags": sorted(sh_tags)[:3],
                    "shared_entities": sorted(sh_ents)[:3],
                    "shared_topics": sorted(sh_topics)[:2],
                    "source": lead.get("source"),
                    "created_at": lead.get("created_at"),
                    "score": round(score, 3),
                }
            )

    return sorted(results, key=lambda x: x["score"], reverse=True)[:limit]


def build_source_reputation_rows(
    source_rows, pulse_rows=None, speed_rows=None, history_rows=None, category_rows=None
):
    pulse_map = {
        str(i.get("source")): int(i.get("count") or i.get("n") or 0)
        for i in (pulse_rows or [])
    }
    speed_map = {
        str(i.get("source")): int(i.get("first_count") or 0) for i in (speed_rows or [])
    }
    history_map = {str(i.get("source")): i for i in (history_rows or [])}

    from collections import defaultdict

    cat_map = defaultdict(list)
    for cr in category_rows or []:
        s = str(cr.get("source") or "")
        if s and len(cat_map[s]) < 3:
            cat_map[s].append(cr["category"])

    results = []
    for row in source_rows or []:
        name = str(row.get("name") or row.get("source") or "").strip()
        if not name:
            continue
        weight = get_source_effective_weight(name)
        hist = history_map.get(name, {})
        l_30d = int(hist.get("lead_count_30d") or 0)
        c_rate = (
            round(int(hist.get("corroborated_lead_count_30d") or 0) / l_30d, 2)
            if l_30d > 0
            else 0.0
        )
        l_rate = (
            round(int(hist.get("solo_lead_count_30d") or 0) / l_30d, 2)
            if l_30d > 0
            else 0.0
        )
        vol_7d = int(hist.get("recent_7d_volume") or 0)
        delta = vol_7d - int(hist.get("previous_7d_volume") or 0)
        first_c = speed_map.get(name, 0)

        results.append(
            {
                "source": name,
                "country": row.get("country") or "",
                "category": row.get("category") or "",
                "top_categories": cat_map.get(name, []),
                "effective_weight": round(weight, 2),
                "trust_tier": (
                    "Висока доверба"
                    if weight >= 1.75
                    else ("Потврден извор" if weight >= 1.3 else "Следен извор")
                ),
                "recent_volume": pulse_map.get(name, 0),
                "speed_first_count": first_c,
                "corroboration_rate": c_rate,
                "lone_lead_rate": l_rate,
                "lead_count_30d": l_30d,
                "trend_label": (
                    "Расте" if delta >= 4 else ("Слабее" if delta <= -4 else "Стабилен ритам")
                ),
                "tendency": (
                    "Често прв на приказната" if first_c >= 5 else "Постепено следење"
                ),
                "last_fetched": row.get("last_fetched"),
                "is_active": row.get("is_active", True),
            }
        )
    return sorted(
        results,
        key=lambda i: (
            i["effective_weight"],
            i["recent_volume"],
            i["speed_first_count"],
        ),
        reverse=True,
    )


def build_editor_analytics_payload(
    profile_stats=None,
    delivery_stats=None,
    top_topics=None,
    top_sources=None,
    tracking_stats=None,
    tracking_perf=None,
    sugg_surface=None,
    sugg_kind=None,
    sugg_period=None,
):
    p, d, t = (profile_stats or {}), (delivery_stats or {}), (tracking_stats or {})
    s7, o7, c7 = (
        int(t.get("sends_7d") or 0),
        int(t.get("opens_7d") or 0),
        int(t.get("clicks_7d") or 0),
    )

    def _perf(rows, kind_map):
        res = []
        for r in rows or []:
            k = str(r.get("delivery_kind") or r.get("suggestion_kind") or "")
            if not k:
                continue
            s, o, c = (
                int(r.get("sends") or r.get("impressions") or 0),
                int(r.get("opens") or r.get("follows") or 0),
                int(r.get("clicks") or r.get("dismissals") or 0),
            )
            res.append(
                {
                    "kind": k,
                    "label": kind_map.get(k, k),
                    "sends": s,
                    "opens": o,
                    "clicks": c,
                    "rate": round((o / s) * 100, 1) if s else 0.0,
                }
            )
        return sorted(res, key=lambda x: x["rate"], reverse=True)

    s_perf = []
    p_map = {r.get("surface"): r for r in (sugg_period or [])}
    for r in sugg_surface or []:
        surf = r.get("surface")
        curr = p_map.get(surf, {})
        rate = round(
            int(r.get("follows") or 0) / int(r.get("impressions") or 1) * 100, 1
        )
        prev_rate = round(
            int(curr.get("previous_follows") or 0)
            / int(curr.get("previous_impressions") or 1)
            * 100,
            1,
        )
        s_perf.append(
            {
                **r,
                "label": {"onboarding": "Водич", "cluster": "Кластер"}.get(surf, surf),
                "conversion_rate": rate,
                "trend_delta": round(rate - prev_rate, 1),
            }
        )

    return {
        "synced_profiles": int(p.get("synced_profiles") or 0),
        "delivery_active": int(d.get("delivery_active") or 0),
        "sends_7d": s7,
        "open_rate_7d": round((o7 / s7) * 100, 1) if s7 else 0.0,
        "delivery_performance": _perf(
            tracking_perf, {"morning": "Утрински", "weekly": "Неделен"}
        ),
        "suggestion_performance": sorted(
            s_perf, key=lambda x: x["conversion_rate"], reverse=True
        ),
        "top_topics": [
            {"topic": r.get("topic"), "n": int(r.get("n") or 0)}
            for r in (top_topics or [])
        ],
        "top_sources": [
            {"source": r.get("source"), "n": int(r.get("n") or 0)}
            for r in (top_sources or [])
        ],
    }


def score_cluster(arts: List[Dict[str, Any]]) -> float:
    if not arts:
        return 0.0
    u_sources = {a["source"] for a in arts}
    cred = sum(get_source_effective_weight(s) for s in u_sources)
    try:
        dt = _coerce_datetime(arts[0]["created_at"]) or datetime.datetime.now()
        hrs = (datetime.datetime.now() - dt).total_seconds() / 3600
    except Exception:
        hrs = 24
    recency = math.exp(-0.115 * hrs)
    clicks = sum(a.get("clicks", 0) or 0 for a in arts)
    return cred * recency * math.log1p(len(arts)) * (1 + math.log1p(clicks) * 0.15)


def score_cluster_for_synthesis(arts: List[Dict[str, Any]]) -> float:
    if not arts:
        return 0.0
    ranked = rank_articles_in_cluster(arts)
    base = score_cluster(ranked)
    src_bonus = 1 + min(0.8, math.log1p(len({a["source"] for a in ranked})) * 0.28)
    ctx_bonus = 1 + min(
        0.35, sum(1 for a in ranked if str(a.get("description")).strip()) * 0.08
    )
    return base * src_bonus * ctx_bonus


def score_cluster_for_homepage(arts: List[Dict[str, Any]]) -> float:
    if not arts:
        return 0.0
    ranked = rank_articles_in_cluster(arts)
    base = score_cluster(ranked)
    w = [get_source_effective_weight(a["source"]) for a in ranked[:3]]
    t_bonus = 1 + max(0.0, min(0.22, (sum(w) / len(w) - 1.0) * 0.16))
    return base * t_bonus * (0.72 if len({a["source"] for a in ranked}) <= 1 else 1.0)


def assess_cluster_synthesis_freshness(
    arts: List[Dict[str, Any]], synth_at
) -> Dict[str, Any]:
    if not arts:
        return {"refresh_needed": False, "reasons": [], "new_article_count": 0}
    ranked = rank_articles_in_cluster(arts)
    s_dt = _coerce_datetime(synth_at)
    if not s_dt:
        return {
            "refresh_needed": True,
            "reasons": ["missing_synthesis"],
            "new_article_count": len(ranked),
        }

    new = [
        a
        for a in ranked
        if (_coerce_datetime(a.get("created_at")) or datetime.datetime.min) > s_dt
    ]
    if not new:
        return {"refresh_needed": False, "reasons": [], "new_article_count": 0}

    reasons = []
    score = 0.0
    if any(
        a["source"] not in {o["source"] for o in ranked if o not in new} for a in new
    ):
        score += 1.0
        reasons.append("new_sources")
    if any(re.findall(r"\b\d+\b", str(a.get("title"))) for a in new):
        score += 1.1
        reasons.append("new_numbers")

    refresh = score >= 2.0 or len(new) >= 4
    if refresh and not reasons:
        reasons.append("volume")

    return {
        "refresh_needed": refresh,
        "new_article_count": len(new),
        "score": score,
        "reasons": reasons,
    }


def is_balanced(arts: List[Dict[str, Any]]) -> bool:
    if len(arts) < BALANCED_COVERAGE_THRESHOLD:
        return False
    reg = get_source_registry()
    return (
        len({a["source"] for a in arts}) >= 4
        or len({reg.get(a["source"], {}).get("category") for a in arts}) >= 2
    )


def publish_event(channel: str, data: dict):
    try:
        redis_client.publish(channel, json.dumps(data, cls=DateTimeEncoder))
    except Exception:
        pass


async def event_stream(channel: str, request=None):
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)
    try:
        while True:
            if request and await request.is_disconnected():
                break
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg:
                yield f"data: {msg['data']}\n\n"
            else:
                yield "retry: 10000\n\n"
            await asyncio.sleep(0.1)
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
