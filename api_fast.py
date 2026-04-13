import os
import secrets
import logging
import datetime
import time
import re
import requests
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from config import validate_required_env, API_MAX_PAGE, API_MAX_Q_LEN
from utils import (
    check_rate_limit, record_runtime_event, 
    cached_response, set_cache, delete_cache
)
from database import db_manager as db
from health import _probe_database, _probe_redis, get_source_statuses
from local_nlp import answer_cluster_question_locally
from ai_engine import _call_ai_async, clean_json_response
from api_helpers import rank_cluster_citations as _rank_cluster_citations
from routes.common import (
    _client_ip_for_request, _apply_security_headers, _is_rate_limited_path, 
    _rate_limit_error_payload, _safe_tracking_redirect_path,
    _resolve_public_ips, _peer_ip
)
from routes import news, intelligence, profile, stats, system
from routes.news import (
    _build_cluster_answer_payload, get_news, 
    chat_cluster_route as chat_cluster,
    ask_cluster_route as ask_cluster
)
from routes.profile import (
    init_profile_sync, get_profile_sync, save_profile_sync,
    get_profile_delivery, save_profile_delivery, save_suggestion_events
)
from routes.stats import (
    get_stats_full, get_sources_route as get_sources,
    control_source_route as control_source
)
from routes.system import (
    health, serve_sw, robots_txt, serve_manifest, proxy_image,
    get_cluster_share_card as og_cluster_image
)

# Dummy for missing og_image
async def og_image():
    return await og_cluster_image("default")

log = logging.getLogger("presek")
log.setLevel(logging.INFO)

validate_required_env()
app = FastAPI(title="Presek API 6.0", version="6.0.0")
_start_time = datetime.datetime.now(datetime.timezone.utc)

_public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live").rstrip("/")
_default_cors_origins = [
    _public_site_url,
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4321", "http://127.0.0.1:4321",
]
_cors_origins = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip() and o != "*"] or _default_cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Sync-Token", "X-Admin-Token", "X-Requested-With"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

@app.middleware("http")
async def apply_runtime_policies(request: Request, call_next):
    start_time = time.time()
    if _is_rate_limited_path(request.url.path):
        client_host = _client_ip_for_request(request)
        is_auth = (request.headers.get("X-Sync-Token") or request.headers.get("X-Admin-Token") or request.cookies.get("presek_session"))
        if not check_rate_limit(client_host, request.url.path, is_authenticated=bool(is_auth)):
            return _apply_security_headers(JSONResponse(status_code=429, content=_rate_limit_error_payload()))

    response = await call_next(request)
    log.info(f"API {request.method} {request.url.path} took {time.time() - start_time:.4f}s")
    return _apply_security_headers(response)

async def serve_static_asset(filename: str):
    return FileResponse(os.path.join("static", filename))

@app.get("/api/delivery/track/{event_type}")
async def track_delivery_event(event_type: str, event_id: int, redirect: str = "/briefing"):
    # This remains in main for redirect logic simplicity, or could move to stats
    # Fetch parent's context to inherit properties
    p = db.execute_one("SELECT sync_token, delivery_kind, channel, target, cluster_id FROM delivery_tracking_events WHERE id = %s", (event_id,))
    if p:
        db.execute(
            "INSERT INTO delivery_tracking_events (parent_event_id, event_type, sync_token, delivery_kind, channel, target, cluster_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (event_id, event_type, p['sync_token'], p['delivery_kind'], p['channel'], p['target'], p['cluster_id']),
            fetch=False
        )
    return RedirectResponse(url=f"{_public_site_url}{_safe_tracking_redirect_path(redirect)}", status_code=302)

app.include_router(news.router)
app.include_router(intelligence.router)
app.include_router(profile.router)
app.include_router(stats.router)
app.include_router(system.router)
