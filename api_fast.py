import os
import secrets
import logging
import datetime
import time
import re
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from config import validate_required_env
from utils import check_rate_limit, record_runtime_event
from routes.common import (
    _client_ip_for_request, _apply_security_headers, _is_rate_limited_path, 
    _rate_limit_error_payload, _safe_tracking_redirect_path
)
from routes import news, intelligence, profile, stats, system

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
_cors_origins = [o.rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip() and o != "*"] or _default_cors_origins

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

@app.get("/api/delivery/track/{event_type}")
async def track_delivery_event(event_type: str, event_id: int, redirect: str = "/briefing"):
    # This remains in main for redirect logic simplicity, or could move to stats
    from database import db_manager as db
    db.execute("INSERT INTO delivery_tracking_events (delivery_id, event_type) VALUES (%s, %s)", (event_id, event_type), fetch=False)
    return RedirectResponse(url=f"{_public_site_url}{_safe_tracking_redirect_path(redirect)}", status_code=302)

app.include_router(news.router)
app.include_router(intelligence.router)
app.include_router(profile.router)
app.include_router(stats.router)
app.include_router(system.router)
