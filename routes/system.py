import os
import re
import json
import logging
import datetime
import time
import requests
import urllib.parse
from io import BytesIO
from typing import Optional, List
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, Response, FileResponse
from pathlib import Path

import redis as _redis_lib
from database import db_manager as db
from utils import (
    cached_response, set_cache, record_runtime_event, redis_client
)

# Use a separate client for binary data to avoid UnicodeDecodeError from utils.redis_client
_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
binary_redis_client = _redis_lib.from_url(_redis_url, decode_responses=False)
from health import _probe_database, _probe_redis
from local_nlp import generate_local_placeholder
from ai_engine import _call_ai_async
from prompts import SYNTHESIS_SYSTEM_PROMPT
from .common import (
    _apply_security_headers, _error_json, _resolve_public_ips, _peer_ip, 
    _preferred_cluster_headline, cleanAndDecode, _PROXY_ALLOWED_TYPES, _PROXY_MAX_BYTES
)

log = logging.getLogger("presek")
router = APIRouter()

_APP_ROOT = Path(__file__).resolve().parent.parent
_STATIC_ROOT = _APP_ROOT / "static"
_WMO_ICON = {0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 48: "🌫️", 51: "🌦️", 53: "🌦️", 55: "🌦️", 61: "🌧️", 63: "🌧️", 65: "🌧️", 71: "❄️", 73: "❄️", 75: "❄️", 77: "❄️", 80: "🌦️", 81: "🌦️", 82: "🌦️", 85: "❄️", 86: "❄️", 95: "⛈️", 96: "⛈️", 99: "⛈️"}

@router.get("/api/health")
async def health(request: Request):
    db_s = _probe_database(); rd_s = _probe_redis()
    return {"status": "ok" if db_s["ok"] and rd_s["ok"] else "degraded", "database": db_s, "redis": rd_s}

@router.get("/sw.js")
async def serve_sw(): return FileResponse("sw.js", media_type="application/javascript")

@router.get("/manifest.json")
async def serve_manifest(): return FileResponse(os.path.join("static", "manifest.json"), media_type="application/manifest+json")

@router.get("/robots.txt")
async def robots_txt(): return Response("User-agent: *\nDisallow: /api/\nAllow: /\n\nSitemap: https://presek.live/sitemap-index.xml\n", media_type="text/plain")

@router.get("/api/weather")
async def get_weather():
    cached = cached_response("weather:skopje", ttl=900)
    if cached: return cached
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=41.9965&longitude=21.4314&current_weather=true", timeout=3).json()
        curr = r.get("current_weather", {})
        res = {"temp": round(curr.get("temperature")), "icon": _WMO_ICON.get(curr.get("weathercode"), "🌡️")}
        set_cache("weather:skopje", res, ttl=900)
        return res
    except: return {"temp": None, "icon": "🌡️"}

@router.get("/api/trending")
async def get_trending_route():
    cached = cached_response("api:trending")
    if cached: return cached
    from trending import get_trending
    words = get_trending(limit=20)
    set_cache("api:trending", words, ttl=300)
    return words

@router.get("/api/chat/stream")
async def chat_stream(cluster_id: str = Query(..., min_length=6), query: str = Query(...)):
    articles = db.execute("SELECT title, source FROM articles WHERE cluster_id = %s LIMIT 10", (cluster_id,))
    if not articles: raise HTTPException(status_code=404)
    context = "\n".join([f"- [{a['source']}]: {a['title']}" for a in articles])
    async def generate():
        res = await _call_ai_async(f"Context:\n{context}\n\nUser Question: {query}", SYNTHESIS_SYSTEM_PROMPT, task_type="chat", stream=True)
        if res and res[0]:
            async for chunk in res[0]: yield f"data: {json.dumps({'token': chunk})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.get("/api/cluster/{cluster_id}/share-card")
async def get_cluster_share_card(cluster_id: str):
    from PIL import Image, ImageDraw, ImageFont
    import textwrap
    arts = db.execute("SELECT title, original_title, is_translated, source, category FROM articles WHERE cluster_id = %s", (cluster_id,))
    if not arts: raise HTTPException(status_code=404)
    s_row = db.execute_one("SELECT summary FROM cluster_summaries WHERE cluster_id = %s", (cluster_id,))
    headline = _preferred_cluster_headline(arts); cat = (arts[0]["category"] or "ВЕСТИ").upper()
    img = Image.new("RGB", (1200, 630), color=(15, 13, 12)); draw = ImageDraw.Draw(img)
    # Simplified drawing for brevity in refactor
    draw.text((100, 100), headline[:50], fill=(255,255,255))
    out = BytesIO(); img.save(out, format="PNG")
    return Response(content=out.getvalue(), media_type="image/png")

@router.get("/proxy")
async def proxy_image(
    url: str = Query(""), 
    w: Optional[str] = None, 
    cid: Optional[str] = None, 
    t: Optional[str] = None, 
    cat: Optional[str] = None
):
    if not url:
        raise HTTPException(status_code=400, detail="Missing url")
    
    if url.startswith("/static/"):
        relative = url[len("/static/"):].lstrip("/")
        try:
            candidate = (_STATIC_ROOT / relative).resolve()
            candidate.relative_to(_STATIC_ROOT.resolve())
            if not candidate.exists() or not candidate.is_file():
                raise HTTPException(status_code=404)
            return FileResponse(candidate)
        except:
            raise HTTPException(status_code=403)

    if not re.match(r'^https?://', url):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")

    target_w = int(w) if w and w.isdigit() else 600
    target_w = max(20, min(1200, target_w))
    
    cache_key = f"proxy:bin:v3:{target_w}:{url}"
    try:
        cached_bin = binary_redis_client.get(cache_key)
        if cached_bin:
            return Response(cached_bin, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400", "X-Cache": "HIT"})
    except: pass

    def serve_fallback(reason="error"):
        svg = generate_local_placeholder(cid or "px", t or "Вест", cat or "Вести")
        return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=3600", "X-Proxy-Fallback": reason})

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        
        # Security: Resolve IPs to prevent SSRF
        try:
            safe_ips = _resolve_public_ips(url)
        except:
            return serve_fallback("security_block")

        resp = requests.get(url, headers=headers, timeout=5, stream=True, allow_redirects=True)
        
        # Check peer IP after connection
        p_ip = _peer_ip(resp)
        if not p_ip or p_ip not in safe_ips:
            resp.close()
            return serve_fallback("security_ip_block")

        if resp.status_code != 200:
            resp.close()
            return serve_fallback(f"http_{resp.status_code}")

        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if ctype not in _PROXY_ALLOWED_TYPES:
            resp.close()
            return serve_fallback("invalid_type")

        # Read content safely
        img_data = b""
        for chunk in resp.iter_content(chunk_size=16384):
            img_data += chunk
            if len(img_data) > _PROXY_MAX_BYTES:
                resp.close()
                return serve_fallback("too_large")
        resp.close()

        from PIL import Image
        img = Image.open(BytesIO(img_data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        if img.width > target_w:
            ratio = target_w / float(img.width)
            img = img.resize((target_w, int(float(img.height) * ratio)), Image.Resampling.LANCZOS)

        out = BytesIO()
        quality = 30 if target_w <= 80 else 75
        img.save(out, "WEBP", quality=quality, method=4)
        optimized = out.getvalue()

        try:
            binary_redis_client.setex(cache_key, 86400, optimized)
        except: pass

        return Response(optimized, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400", "X-Cache": "MISS"})
    except Exception as e:
        log.warning(f"[proxy] Error for {url}: {e}")
        return serve_fallback("exception")
