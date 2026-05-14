import os
import re
import logging
import time
import urllib.parse
import secrets
from collections import defaultdict
from io import BytesIO
from typing import Optional
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import Response, FileResponse
from pathlib import Path
from prometheus_client import Counter

import redis as _redis_lib
from database import db_manager as db
from utils import cached_response, set_cache

log = logging.getLogger("presek.routes.system")

# Prometheus metrics
PROXY_REQUESTS = Counter(
    "proxy_requests_total",
    "Total number of proxy requests",
    ["status", "reason"],
)
PROXY_BYTES = Counter(
    "proxy_bytes_total",
    "Total bytes transferred through proxy",
)
PROXY_CACHE_HITS = Counter(
    "proxy_cache_hits_total",
    "Total number of proxy cache hits",
)
PROXY_CACHE_MISSES = Counter(
    "proxy_cache_misses_total",
    "Total number of proxy cache misses",
)

# Use a separate client for binary data to avoid UnicodeDecodeError from utils.redis_client
_redis_url = os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
try:
    binary_redis_client = _redis_lib.from_url(_redis_url, decode_responses=False)
    binary_redis_client.ping()
except Exception as e:
    log.warning(f"Binary Redis client failed to connect to {_redis_url}: {e}")
    binary_redis_client = _redis_lib.from_url(
        "redis://localhost:6379/0", decode_responses=False
    )
from health import _probe_database, _probe_redis
from nlp import generate_local_placeholder
from version import version_payload
from utils import _resolve_public_ips, _peer_ip
from .common import cleanAndDecode, _PROXY_ALLOWED_TYPES, _PROXY_MAX_BYTES
from .security import validate_cluster_id

log = logging.getLogger("presek")
router = APIRouter()
_STARTED_AT = time.time()

_FRESHNESS_EXPR = "COALESCE(ingested_at, created_at)"

_APP_ROOT = Path(__file__).resolve().parent.parent
_STATIC_ROOT = _APP_ROOT / "static"
_WMO_ICON = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌦️",
    55: "🌦️",
    61: "🌧️",
    63: "🌧️",
    65: "🌧️",
    71: "❄️",
    73: "❄️",
    75: "❄️",
    77: "❄️",
    80: "🌦️",
    81: "🌦️",
    82: "🌦️",
    85: "❄️",
    86: "❄️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}


@router.get("/health")
async def health(request: Request):
    admin_token = (os.environ.get("PRESEK_ADMIN_TOKEN") or "").strip()
    provided_token = (request.headers.get("X-Admin-Token") or "").strip()
    is_admin = bool(
        admin_token
        and provided_token
        and secrets.compare_digest(provided_token, admin_token)
    )

    db_s = _probe_database()
    rd_s = _probe_redis()

    if not is_admin:
        # Omit sensitive details for public status
        for probe in [db_s, rd_s]:
            probe.pop("url", None)
            probe.pop("error", None)
            probe.pop("config", None)

    return {
        "status": "ok" if db_s["ok"] and rd_s["ok"] else "degraded",
        **version_payload(),
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "database": db_s,
        "redis": rd_s,
    }


@router.get("/sw.js")
async def serve_sw():
    return FileResponse("sw.js", media_type="application/javascript")


@router.get("/manifest.json")
async def serve_manifest():
    return FileResponse(
        os.path.join("static", "manifest.json"), media_type="application/manifest+json"
    )


@router.get("/robots.txt")
async def robots_txt():
    return Response(
        "User-agent: *\nDisallow: /api/\nAllow: /\n\nSitemap: https://presek.live/sitemap-index.xml\n",
        media_type="text/plain",
    )


@router.get("/categories")
async def get_categories():
    """Returns the canonical list of geographic categories for Pulse filtering."""
    from nlp.categories import ALLOWED_CATEGORIES

    # Pulse page expects { categories: [ { name: "..." }, ... ] }
    items = [{"name": cat} for cat in sorted(list(ALLOWED_CATEGORIES))]
    return {"categories": items}


@router.get("/weather")
async def get_weather(lang: Optional[str] = "sr"):
    city = "skopje" if lang == "mk" else "beograd"
    cache_key = f"weather:{city}"
    cached = cached_response(cache_key, ttl=900)
    if cached:
        return cached
    try:
        import httpx

        # Lat/Lon: Skopje (41.99, 21.43), Belgrade (44.78, 20.44)
        lat = 41.9965 if lang == "mk" else 44.7866
        lon = 21.4314 if lang == "mk" else 20.4489

        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            )
        r = response.json()
        curr = r.get("current_weather", {})
        temp = curr.get("temperature")
        res = {
            "temp": round(temp) if temp is not None else None,
            "icon": _WMO_ICON.get(curr.get("weathercode"), "🌡️"),
            "city": "Skopje" if lang == "mk" else "Beograd",
        }
        set_cache(cache_key, res, ttl=900)
        return res
    except Exception as e:
        log.debug(f"Failed to fetch weather for {city}: {e}")
        return {"temp": None, "icon": "🌡️", "city": "Skopje" if lang == "mk" else "Beograd"}


@router.get("/trending")
async def get_trending_route(lang: Optional[str] = "sr"):
    cache_key = f"api:trending:{lang}"
    cached = cached_response(cache_key)
    if cached:
        return cached
    from trending import get_trending

    target_country = "MK" if lang == "mk" else "RS"
    words = get_trending(limit=20, country=target_country)
    set_cache(cache_key, words, ttl=300)
    return words


@router.get("/navigation")
async def get_navigation(lang: Optional[str] = "sr"):
    """Returns high-intelligence dynamic navigation with activity thresholds."""
    cache_key = f"api:navigation:v6:{lang}"
    cached = cached_response(cache_key)
    if cached:
        return cached

    from config import BREAKING_SCORE_THRESHOLD
    from utils import score_cluster
    from .intelligence import get_top_entities

    # Localized Labels Mapping
    L = {
        "mk": {
            "geography": "Географија",
            "balkan": "Балкан",
            "evropa": "Европа",
            "svet": "Свет",
            "news": "Вести",
            "politika": "Политика",
            "ekonomija": "Економија",
            "sport": "Спорт",
            "kriminal": "Криминал",
            "local_city": "Скопје",
            "local_sub": "Skopje",
            "magazine": "Магазин",
            "kultura": "Култура",
            "zivot": "Живот",
            "tehnologija": "Технологија",
            "zdravje": "Здравје",
            "zabava": "Забава",
            "fokus": "Во Фокус",
        },
        "sr": {
            "geography": "Geografija",
            "balkan": "Balkan",
            "evropa": "Evropa",
            "svet": "Svet",
            "news": "Vesti",
            "politika": "Politika",
            "ekonomija": "Ekonomija",
            "sport": "Sport",
            "kriminal": "Kriminal",
            "local_city": "Beograd",
            "local_sub": "Beograd",
            "magazine": "Magazin",
            "kultura": "Kultura",
            "zivot": "Život",
            "tehnologija": "Tehnologija",
            "zdravje": "Zdravlje",
            "zabava": "Zabava",
            "fokus": "U Fokusu",
        },
    }.get(lang, "sr")
    if isinstance(L, str):  # Default fallback
        L = {
            "geography": "Geografija",
            "balkan": "Balkan",
            "evropa": "Evropa",
            "svet": "Svet",
            "news": "Vesti",
            "politika": "Politika",
            "ekonomija": "Ekonomija",
            "sport": "Sport",
            "kriminal": "Kriminal",
            "local_city": "Beograd",
            "local_sub": "Beograd",
            "magazine": "Magazin",
            "kultura": "Kultura",
            "zivot": "Život",
            "tehnologija": "Tehnologija",
            "zdravje": "Zdravlje",
            "zabava": "Zabava",
            "fokus": "U Fokusu",
        }

    # 1. LIVE / BREAKING (Last 24h)
    breaking_items = []
    target_country = "MK" if lang == "mk" else "RS"

    recent_clusters = await db.async_execute(
        f"""
        SELECT m.cluster_id, 
               (SELECT title FROM articles WHERE cluster_id = m.cluster_id AND country = %s ORDER BY created_at DESC LIMIT 1) as title,
               (SELECT COALESCE(ingested_at, created_at) FROM articles WHERE cluster_id = m.cluster_id AND country = %s ORDER BY COALESCE(ingested_at, created_at) DESC LIMIT 1) as created_at
        FROM cluster_metadata m
        WHERE EXISTS (SELECT 1 FROM articles a WHERE a.cluster_id = m.cluster_id AND a.country = %s)
          AND m.updated_at >= NOW() - INTERVAL '24 hours'
        ORDER BY m.updated_at DESC LIMIT 15
    """, (target_country, target_country, target_country)
    )

    for c in recent_clusters:
        if not c.get("title"):
            continue
        arts = await db.async_execute(
            "SELECT * FROM articles WHERE cluster_id = %s", (c["cluster_id"],)
        )
        if score_cluster(arts) >= BREAKING_SCORE_THRESHOLD:
            created_at = c.get("created_at")
            breaking_items.append(
                {
                    "label": cleanAndDecode(c["title"])[:80]
                    + ("..." if len(c["title"]) > 80 else ""),
                    "href": f"/cluster/{c['cluster_id']}",
                    "type": "breaking",
                    "created_at": created_at.isoformat() if created_at else None,
                }
            )
            if len(breaking_items) >= 4:
                break

    # 2. Dynamic Activity (24h lookback)
    activity = await db.async_execute(
        f"""
        SELECT category, topic, COUNT(DISTINCT cluster_id) as n
        FROM articles
        WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'
          AND country = %s
          AND category IS NOT NULL AND category != ''
          AND topic IS NOT NULL AND topic != ''
        GROUP BY category, topic
    """, (target_country,)
    )

    sub_activity = await db.async_execute(
        f"""
        SELECT subcategory, COUNT(DISTINCT cluster_id) as n
        FROM articles 
        WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'
          AND country = %s
          AND subcategory IS NOT NULL AND subcategory != ''
        GROUP BY subcategory
    """, (target_country,)
    )

    cat_act = defaultdict(int)
    top_act = defaultdict(int)
    for r in activity:
        if r["category"]:
            cat_act[r["category"]] += r["n"]
        if r["topic"]:
            top_act[r["topic"]] += r["n"]

    sub_act = {r["subcategory"]: r["n"] for r in sub_activity}

    # 3. GEOGRAPHY
    geo_items = []
    for label, display in [
        ("Balkan", L["balkan"]),
        ("Evropa", L["evropa"]),
        ("Svet", L["svet"]),
    ]:
        count = cat_act.get(label, 0)
        geo_items.append(
            {
                "label": display,
                "href": f"/?category={urllib.parse.quote(label)}",
                "count": count,
            }
        )

    # 4. CORE NEWS
    news_items = []
    core_news = [
        ("Politika", L["politika"]),
        ("Ekonomija", L["ekonomija"]),
        ("Sport", L["sport"]),
        ("Kriminal", L["kriminal"]),
    ]
    for label, display in core_news:
        count = top_act.get(label, 0)
        news_items.append(
            {
                "label": display,
                "href": f"/?topic={urllib.parse.quote(label)}",
                "count": count,
            }
        )

    # Add Local Anchor
    local_label = L["local_city"]
    local_sub = L["local_sub"]
    local_count = sub_act.get(local_sub, 0)
    news_items.append(
        {
            "label": local_label,
            "href": f"/?subcategory={urllib.parse.quote(local_sub)}",
            "count": local_count,
        }
    )

    # 5. MAGAZINE
    magazine_items = []
    magazine_topics = [
        ("Kultura", L["kultura"]),
        ("Zivot", L["zivot"]),
        ("Tehnologija", L["tehnologija"]),
        ("Zdravje", L["zdravje"]),
        ("Zabava", L["zabava"]),
    ]
    for label, display in magazine_topics:
        count = top_act.get(label, 0)
        magazine_items.append(
            {
                "label": display,
                "href": f"/?topic={urllib.parse.quote(label)}",
                "count": count,
            }
        )

    # 6. TRENDING STORIES
    trending_entities = await get_top_entities(limit=8, lang=lang)
    entities = [
        {
            "label": f"#{e['name']}",
            "href": f"/?entity={urllib.parse.quote(e['name'])}",
            "type": "trending_tag",
        }
        for e in trending_entities
        if e["total_mentions"] > 5
    ]

    res = {
        "breaking": breaking_items,
        "sections": [
            {"label": L["geography"], "items": geo_items, "type": "core"},
            {"label": L["news"], "items": news_items, "type": "dynamic"},
            {"label": L["magazine"], "items": magazine_items, "type": "magazine"},
            {"label": L["fokus"], "items": entities[:5], "type": "trending"},
        ],
    }
    set_cache(cache_key, res, ttl=300)
    return res


@router.get("/cluster/{cluster_id}/share-card")
async def get_cluster_share_card(cluster_id: str):
    # Validate cluster_id
    validate_cluster_id(cluster_id)

    from PIL import Image, ImageDraw, ImageFont
    import textwrap

    try:
        # 1. Gather Cluster Info
        arts = await db.async_execute(
            "SELECT title, source, category, image_url, local_image_path FROM articles WHERE cluster_id = %s ORDER BY created_at DESC",
            (cluster_id,),
        )
        if not arts:
            raise HTTPException(status_code=404)

        meta = await db.async_execute_one(
            "SELECT representative_image, dominant_color FROM cluster_metadata WHERE cluster_id = %s",
            (cluster_id,),
        )
        headline = cleanAndDecode(arts[0]["title"])
        source_count = len(set(a["source"] for a in arts))
        cat = (arts[0]["category"] or "vesti").upper()

        # 2. Setup Canvas (OG Standard: 1200x630)
        img = Image.new("RGB", (1200, 630), color=(15, 13, 12))

        # 3. Background Image with Dimmer
        bg_url = (meta or {}).get("representative_image") or arts[0]["image_url"]
        local_bg = arts[0]["local_image_path"]

        bg_img = None
        try:
            if local_bg:
                local_path = (_STATIC_ROOT / local_bg.lstrip("/")).resolve()
                allowed_roots = [
                    _STATIC_ROOT.resolve(),
                    (_APP_ROOT.parent.parent / "shared" / "static").resolve(),
                ]
                if (
                    any(
                        _path_is_relative_to(local_path, root) for root in allowed_roots
                    )
                    and local_path.exists()
                ):
                    bg_img = Image.open(local_path)

            if not bg_img and bg_url and bg_url.startswith("http"):
                safe_ips = _resolve_public_ips(bg_url)
                import httpx

                async with httpx.AsyncClient(
                    timeout=3.0, follow_redirects=True
                ) as client:
                    async with client.stream("GET", bg_url) as resp:
                        p_ip = _peer_ip(resp)
                        ctype = (
                            str(resp.headers.get("Content-Type", ""))
                            .split(";")[0]
                            .strip()
                        )
                        if (
                            p_ip
                            and p_ip in safe_ips
                            and resp.status_code == 200
                            and ctype in _PROXY_ALLOWED_TYPES
                        ):
                            content = b""
                            async for chunk in resp.aiter_bytes(chunk_size=16384):
                                content += chunk
                                if len(content) > _PROXY_MAX_BYTES:
                                    content = b""
                                    break
                            if content:
                                bg_img = Image.open(BytesIO(content))
        except Exception as e:
            log.debug(f"[system] Error loading background image: {e}")
            pass

        if bg_img:
            # Resize and crop to fill
            bg_img = bg_img.convert("RGB")
            ratio = max(1200 / bg_img.width, 630 / bg_img.height)
            bg_img = bg_img.resize(
                (int(bg_img.width * ratio), int(bg_img.height * ratio)),
                Image.Resampling.LANCZOS,
            )
            img.paste(
                bg_img, (int((1200 - bg_img.width) / 2), int((630 - bg_img.height) / 2))
            )

            # Add Dark Overlay
            overlay = Image.new("RGBA", (1200, 630), (0, 0, 0, 160))
            img.paste(overlay, (0, 0), overlay)

        draw = ImageDraw.Draw(img)

        # 4. Load Fonts
        font_path_serif = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
        font_path_sans = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        try:
            f_title = ImageFont.truetype(font_path_serif, 72)
            f_kicker = ImageFont.truetype(font_path_sans, 32)
            f_footer = ImageFont.truetype(font_path_sans, 24)
        except (IOError, OSError) as e:
            log.debug(f"[system] Font loading error: {e}, using default")
            f_title = f_kicker = f_footer = ImageFont.load_default()

        # 5. Draw Branding (Masthead)
        draw.text((90, 80), "PRESEK.rs", fill=(185, 28, 28), font=f_title)  # NYT Red
        draw.rectangle([90, 165, 450, 168], fill=(185, 28, 28))  # Underline

        # 6. Draw Kicker
        draw.text(
            (90, 200),
            f"{cat} · {source_count} izvori IZVESTUVAAT",
            fill=(209, 213, 235),
            font=f_kicker,
        )

        # 7. Draw Headline (Wrapped)
        lines = textwrap.wrap(headline, width=32)
        y_text = 270
        for line in lines[:3]:  # Limit to 3 lines
            draw.text((90, y_text), line, fill=(255, 255, 255), font=f_title)
            y_text += 85

        # 8. Footer Info
        draw.text(
            (90, 550), "SITE izvori NA EDNO MESTO", fill=(156, 163, 175), font=f_footer
        )
        draw.text(
            (1110, 550), "presek.live", fill=(255, 255, 255), font=f_footer, anchor="ra"
        )

        out = BytesIO()
        img.save(out, format="PNG")
        return Response(
            content=out.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        log.error(f"OG Image Error: {e}", exc_info=True)
        # Fallback to simple image
        img = Image.new("RGB", (1200, 630), color=(15, 13, 12))
        out = BytesIO()
        img.save(out, format="PNG")
        return Response(content=out.getvalue(), media_type="image/png")


def _path_is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


@router.get("/proxy")
async def proxy_image(
    url: str = Query(""),
    w: Optional[str] = None,
    cid: Optional[str] = None,
    t: Optional[str] = None,
    cat: Optional[str] = None,
):
    """
    Proxy images to avoid CORS and mixed content issues.
    
    Args:
        url: The URL of the image to proxy.
        w: The width of the image (optional).
        cid: The cluster ID (optional).
        t: The title of the image (optional).
        cat: The category of the image (optional).
    
    Returns:
        The proxied image as a Response.
    
    Raises:
        HTTPException: If the URL is invalid or missing.
    """
    if not url:
        PROXY_REQUESTS.labels(status="400", reason="missing_url").inc()
        raise HTTPException(status_code=400, detail="Nedostasuva URL adresa")

    if url.startswith("/static/"):
        relative = url[len("/static/") :].lstrip("/")
        try:
            # Important: In production, static/generated and static/uploads are symlinks
            # to a shared directory outside the release tree. We must allow both.
            candidate = (_STATIC_ROOT / relative).resolve()

            allowed_roots = [
                _STATIC_ROOT.resolve(),
                (
                    _APP_ROOT.parent.parent / "shared" / "static"
                ).resolve(),  # Production shared root
            ]

            is_safe = False
            for root in allowed_roots:
                try:
                    candidate.relative_to(root)
                    is_safe = True
                    break
                except ValueError:
                    continue

            if not is_safe:
                log.warning(
                    f"[proxy/static] Path traversal attempt or invalid root for {url}: {candidate}"
                )
                raise HTTPException(status_code=403)

            if not candidate.exists() or not candidate.is_file():
                log.warning(f"[proxy/static] File not found: {candidate}")
                PROXY_REQUESTS.labels(status="404", reason="file_not_found").inc()
                raise HTTPException(status_code=404)
            return FileResponse(candidate)
        except HTTPException:
            raise
        except Exception as e:
            log.warning(f"[proxy/static] Access denied for {url}: {e}")
            raise HTTPException(status_code=403)

    if not re.match(r"^https?://", url):
        PROXY_REQUESTS.labels(status="400", reason="invalid_scheme").inc()
        raise HTTPException(status_code=400, detail="Nevalidna URL sema")
    
    # Additional URL validation for common issues
    try:
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.netloc:
            raise HTTPException(status_code=400, detail=f"Invalid URL - missing domain: {url}")
        if parsed_url.netloc.endswith(('.localhost', 'localhost', '127.0.0.1', '0.0.0.0')):
            raise HTTPException(status_code=400, detail=f"Localhost URLs not allowed: {url}")
        if len(url) > 2048:
            raise HTTPException(status_code=400, detail="URL too long")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid URL format: {e}")

    target_w = int(w) if w and w.isdigit() else 600
    target_w = max(20, min(1200, target_w))

    cache_key = f"proxy:bin:v3:{target_w}:{url}"
    try:
        cached_bin = binary_redis_client.get(cache_key)
        if cached_bin:
            PROXY_CACHE_HITS.inc()
            PROXY_REQUESTS.labels(status="200", reason="cache_hit").inc()
            return Response(
                cached_bin,
                media_type="image/webp",
                headers={"Cache-Control": "public, max-age=86400", "X-Cache": "HIT"},
            )
    except Exception as e:
        log.debug(f"Binary Redis cache lookup failed: {e}")
        PROXY_REQUESTS.labels(status="500", reason="cache_error").inc()

    def serve_fallback(reason="error"):
        svg = generate_local_placeholder(cid or "px", t or "vest", cat or "vesti")
        log.warning(f"[proxy] Serving fallback for {url or 'unknown'}: {reason}")
        
        # Add diagnostic information to the SVG for debugging
        diagnostic_svg = svg.replace("</svg>", f"""
    <text x="40" y="430" font-family="sans-serif" font-size="12" fill="white" opacity="0.7">
        Proxy Fallback: {reason}
    </text>
    <text x="40" y="445" font-family="sans-serif" font-size="10" fill="white" opacity="0.7">
        URL: {url[:50] if url else 'unknown'}...
    </text>
</svg>""")
        
        return Response(
            diagnostic_svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Proxy-Fallback": reason,
                "X-Debug-Reason": reason,
                "X-Diagnostic-Info": f"Fallback served for {url or 'unknown'}: {reason}",
            },
        )

    try:
        # 1. Fast path: check if we have a locally saved version in the DB
        local_img_row = await db.async_execute_one(
            "SELECT local_image_path FROM articles WHERE image_url = %s AND local_image_path IS NOT NULL LIMIT 1",
            (url,),
        )
        img_data = None
        if local_img_row:
            local_rel = local_img_row["local_image_path"].lstrip("/")
            if local_rel.startswith("static/"):
                local_rel = local_rel[len("static/") :].lstrip("/")

            local_full = (_STATIC_ROOT / local_rel).resolve()
            allowed_roots = [
                _STATIC_ROOT.resolve(),
                (_APP_ROOT.parent.parent / "shared" / "static").resolve(),
            ]
            is_safe_local = False
            for root in allowed_roots:
                try:
                    local_full.relative_to(root)
                    is_safe_local = True
                    break
                except ValueError:
                    continue

            if not is_safe_local:
                log.warning(
                    f"[proxy] Blocked unsafe local image path for {url}: {local_full}"
                )
            elif local_full.exists() and local_full.is_file():
                with open(local_full, "rb") as f:
                    img_data = f.read()
                log.info(f"[proxy] Using local master for {url}")

        # 2. Slow path: fetch from remote if no local version exists
        if not img_data:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": url,
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }

            # Security: Resolve IPs to prevent SSRF
            try:
                safe_ips = _resolve_public_ips(url)
            except Exception as e:
                log.debug(f"SSRF: Failed to resolve IPs for {url}: {e}")
                return serve_fallback("security_block")

            import httpx

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                try:
                    async with client.stream("GET", url, headers=headers) as resp:
                        # Check peer IP after connection
                        p_ip = _peer_ip(resp)
                        if not p_ip or p_ip not in safe_ips:
                            return serve_fallback("security_ip_block")

                        if resp.status_code == 403:
                            log.warning(f"[proxy] Hotlinking blocked for {url} - trying with referer")
                            # Try again with different headers to bypass hotlinking protection
                            headers["Referer"] = f"https://{parsed_url.netloc}/"
                            async with client.stream("GET", url, headers=headers) as resp2:
                                if resp2.status_code == 200:
                                    resp = resp2
                                else:
                                    return serve_fallback(f"hotlink_blocked_{resp2.status_code}")
                        elif resp.status_code == 404:
                            return serve_fallback("not_found")
                        elif resp.status_code != 200:
                            return serve_fallback(f"http_{resp.status_code}")

                        ctype = (
                            str(resp.headers.get("Content-Type", ""))
                            .split(";")[0]
                            .strip()
                        )
                        if ctype not in _PROXY_ALLOWED_TYPES:
                            return serve_fallback("invalid_type")

                        # Read content safely
                        img_data = b""
                        async for chunk in resp.aiter_bytes(chunk_size=16384):
                            img_data += chunk
                            if len(img_data) > _PROXY_MAX_BYTES:
                                log.warning(f"[proxy] Image too large: {url}")
                                PROXY_REQUESTS.labels(status="400", reason="too_large").inc()
                                return serve_fallback("too_large")
                except Exception as e:
                    log.error(f"[proxy] Fetch failed for {url}: {e}", exc_info=True)
                    PROXY_REQUESTS.labels(status="500", reason="fetch_failed").inc()
                    return serve_fallback("fetch_failed")

        if not img_data:
            return serve_fallback("no_data")

        from PIL import Image

        img = Image.open(BytesIO(img_data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        if img.width > target_w:
            ratio = target_w / float(img.width)
            img = img.resize(
                (target_w, int(float(img.height) * ratio)), Image.Resampling.LANCZOS
            )

        out = BytesIO()
        quality = 30 if target_w <= 80 else 75
        img.save(out, "WEBP", quality=quality, method=4)
        optimized = out.getvalue()

        try:
            binary_redis_client.setex(cache_key, 86400, optimized)
            log.info(f"[proxy] Cached image: {url}")
        except Exception as e:
            log.warning(f"[proxy] Failed to cache binary image: {e}")

        log.info(f"[proxy] Successfully proxied image: {url}")
        PROXY_CACHE_MISSES.inc()
        PROXY_BYTES.inc(len(optimized))
        PROXY_REQUESTS.labels(status="200", reason="cache_miss").inc()
        return Response(
            optimized,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400", "X-Cache": "MISS"},
        )
    except Exception as e:
        log.error(f"[proxy] Error for {url}: {e}", exc_info=True)
        # Add more specific error logging for common issues
        if "Connection refused" in str(e):
            log.error(f"[proxy] Connection refused for {url} - service may be down")
        elif "timeout" in str(e).lower():
            log.error(f"[proxy] Timeout fetching {url} - slow response")
        elif "403" in str(e) or "404" in str(e):
            log.error(f"[proxy] Access denied for {url} - hotlinking blocked or invalid URL")
        return serve_fallback("exception")
