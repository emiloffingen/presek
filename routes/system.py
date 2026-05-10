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

import redis as _redis_lib
from database import db_manager as db
from utils import cached_response, set_cache

log = logging.getLogger("presek.routes.system")

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
async def get_weather():
    cached = cached_response("weather:skopje", ttl=900)
    if cached:
        return cached
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast?latitude=41.9965&longitude=21.4314&current_weather=true"
            )
        r = response.json()
        curr = r.get("current_weather", {})
        temp = curr.get("temperature")
        res = {
            "temp": round(temp) if temp is not None else None,
            "icon": _WMO_ICON.get(curr.get("weathercode"), "🌡️"),
        }
        set_cache("weather:skopje", res, ttl=900)
        return res
    except Exception as e:
        log.debug(f"Failed to fetch weather: {e}")
        return {"temp": None, "icon": "🌡️"}


@router.get("/trending")
async def get_trending_route():
    cached = cached_response("api:trending")
    if cached:
        return cached
    from trending import get_trending

    words = get_trending(limit=20)
    set_cache("api:trending", words, ttl=300)
    return words


@router.get("/navigation")
async def get_navigation():
    """Returns high-intelligence dynamic navigation with activity thresholds."""
    cache_key = "api:navigation:v5"
    cached = cached_response(cache_key)
    if cached:
        return cached

    from config import BREAKING_SCORE_THRESHOLD
    from utils import score_cluster
    from .intelligence import get_top_entities

    # 1. LIVE / BREAKING (Last 24h)
    breaking_items = []
    recent_clusters = await db.async_execute(
        """
        SELECT m.cluster_id, 
               (SELECT title FROM articles WHERE cluster_id = m.cluster_id ORDER BY created_at DESC LIMIT 1) as title,
               (SELECT COALESCE(ingested_at, created_at) FROM articles WHERE cluster_id = m.cluster_id ORDER BY COALESCE(ingested_at, created_at) DESC LIMIT 1) as created_at
        FROM cluster_metadata m
        WHERE m.updated_at >= NOW() - INTERVAL '24 hours'
        ORDER BY m.updated_at DESC LIMIT 15
    """
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
    # Count article-level classifications so navigation does not inherit stale
    # mixed-topic/category arrays from cluster metadata.
    activity = await db.async_execute(
        f"""
        SELECT category, topic, COUNT(DISTINCT cluster_id) as n
        FROM articles
        WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'
          AND category IS NOT NULL AND category != ''
          AND topic IS NOT NULL AND topic != ''
        GROUP BY category, topic
    """
    )

    # Subcategory still needs articles table but it's narrow
    sub_activity = await db.async_execute(
        f"""
        SELECT subcategory, COUNT(DISTINCT cluster_id) as n
        FROM articles 
        WHERE {_FRESHNESS_EXPR} >= NOW() - INTERVAL '24 hours'
          AND subcategory IS NOT NULL AND subcategory != ''
        GROUP BY subcategory
    """
    )

    cat_act = defaultdict(int)
    top_act = defaultdict(int)
    for r in activity:
        if r["category"]:
            cat_act[r["category"]] += r["n"]
        if r["topic"]:
            top_act[r["topic"]] += r["n"]

    sub_act = {r["subcategory"]: r["n"] for r in sub_activity}

    # 3. GEOGRAPHY (Excluding Macedonia as it's the home default)
    # The header "Географија" is defined by the section label in the final payload structure
    geo_items = []
    for label, display in [
        ("Балкан", "Балкан"),
        ("Европа", "Европа"),
        ("Свет", "Свет"),
    ]:
        count = cat_act.get(label, 0)
        geo_items.append(
            {
                "label": display,
                "href": f"/?category={urllib.parse.quote(display)}",
                "count": count,
            }
        )

    # 4. CORE NEWS (The Pillars + Skopje)
    news_items = []
    core_news = ["Политика", "Економија", "Спорт", "Криминал"]
    for label in core_news:
        count = top_act.get(label, 0)
        news_items.append(
            {
                "label": label,
                "href": f"/?topic={urllib.parse.quote(label)}",
                "count": count,
            }
        )

    # Add Skopje as the local anchor
    skopje_count = sub_act.get("Скопје", 0)
    news_items.append(
        {"label": "Скопје", "href": "/?subcategory=Скопје", "count": skopje_count}
    )

    # 5. MAGAZINE (Lifestyle & Culture)
    magazine_items = []
    magazine_topics = ["Култура", "Живот"]
    for label in magazine_topics:
        count = top_act.get(label, 0)
        magazine_items.append(
            {
                "label": label,
                "href": f"/?topic={urllib.parse.quote(label)}",
                "count": count,
            }
        )

    tech_count = top_act.get("Технологија", 0)
    magazine_items.append(
        {"label": "Технологија", "href": "/?topic=Технологија", "count": tech_count}
    )

    health_count = top_act.get("Здравје", 0)
    magazine_items.append(
        {"label": "Здравје", "href": "/?topic=Здравје", "count": health_count}
    )

    entertainment_count = top_act.get("Забава", 0)
    magazine_items.append(
        {"label": "Забава", "href": "/?topic=Забава", "count": entertainment_count}
    )

    # 6. TRENDING STORIES (Top Entities)
    trending_entities = await get_top_entities(limit=8)
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
            {"label": "Географија", "items": geo_items, "type": "core"},
            {"label": "Вести", "items": news_items, "type": "dynamic"},
            {"label": "Магазин", "items": magazine_items, "type": "magazine"},
            {"label": "Во Фокус", "items": entities[:5], "type": "trending"},
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
        cat = (arts[0]["category"] or "ВЕСТИ").upper()

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
        draw.text((90, 80), "ПРЕСЕК.мк", fill=(185, 28, 28), font=f_title)  # NYT Red
        draw.rectangle([90, 165, 450, 168], fill=(185, 28, 28))  # Underline

        # 6. Draw Kicker
        draw.text(
            (90, 200),
            f"{cat} · {source_count} ИЗВОРИ ИЗВЕСТУВААТ",
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
            (90, 550), "СИТЕ ИЗВОРИ НА ЕДНО МЕСТО", fill=(156, 163, 175), font=f_footer
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
    if not url:
        raise HTTPException(status_code=400, detail="Недостасува УРЛ адреса")

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
                raise HTTPException(status_code=404)
            return FileResponse(candidate)
        except HTTPException:
            raise
        except Exception as e:
            log.warning(f"[proxy/static] Access denied for {url}: {e}")
            raise HTTPException(status_code=403)

    if not re.match(r"^https?://", url):
        raise HTTPException(status_code=400, detail="Невалидна УРЛ шема")

    target_w = int(w) if w and w.isdigit() else 600
    target_w = max(20, min(1200, target_w))

    cache_key = f"proxy:bin:v3:{target_w}:{url}"
    try:
        cached_bin = binary_redis_client.get(cache_key)
        if cached_bin:
            return Response(
                cached_bin,
                media_type="image/webp",
                headers={"Cache-Control": "public, max-age=86400", "X-Cache": "HIT"},
            )
    except Exception as e:
        log.debug(f"Binary Redis cache lookup failed: {e}")

    def serve_fallback(reason="error"):
        svg = generate_local_placeholder(cid or "px", t or "Вест", cat or "Вести")
        return Response(
            svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Proxy-Fallback": reason,
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

                        if resp.status_code != 200:
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
                                return serve_fallback("too_large")
                except Exception as e:
                    log.error(f"[proxy] Fetch failed for {url}: {e}")
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
        except Exception as e:
            log.debug(f"Failed to cache binary image: {e}")

        return Response(
            optimized,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400", "X-Cache": "MISS"},
        )
    except Exception as e:
        log.warning(f"[proxy] Error for {url}: {e}")
        return serve_fallback("exception")
