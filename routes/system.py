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

from database import db_manager as db
from utils import (
    cached_response, set_cache, record_runtime_event, redis_client
)
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
async def proxy_image(url: str = Query(""), w: Optional[str] = None, cid: Optional[str] = None, t: Optional[str] = None, cat: Optional[str] = None):
    if not url: raise HTTPException(status_code=400)
    if url.startswith("/static/"):
        rel = url[len("/static/"):].lstrip("/")
        cand = (_STATIC_ROOT / rel).resolve()
        if not cand.exists(): raise HTTPException(status_code=404)
        return FileResponse(cand)
    
    target_w = int(w) if w and w.isdigit() else 600
    cache_key = f"proxy:bin:v3:{target_w}:{url}"
    cached = redis_client.get(cache_key)
    if cached: return Response(cached, media_type="image/webp")

    try:
        resp = requests.get(url, timeout=5, stream=True)
        if resp.status_code != 200: return Response(generate_local_placeholder(cid or "px", t or "Вест", cat or "Вести"), media_type="image/svg+xml")
        from PIL import Image
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        if img.width > target_w: img = img.resize((target_w, int(img.height * (target_w/img.width))), Image.Resampling.LANCZOS)
        out = BytesIO(); img.save(out, "WEBP", quality=75); data = out.getvalue()
        redis_client.setex(cache_key, 86400, data)
        return Response(data, media_type="image/webp")
    except: return Response(generate_local_placeholder(cid or "px", t or "Вест", cat or "Вести"), media_type="image/svg+xml")
