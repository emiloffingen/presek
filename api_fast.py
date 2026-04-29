import os
import secrets
import json
import datetime
import time
import re
import importlib.util
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import fastapi
if not hasattr(fastapi, "responses"):
    import fastapi.responses
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

import database
from database import db_manager as db
import config
from version import APP_VERSION, APP_VERSION_LABEL, get_full_version_info

# Initialize logging early (before other imports)
from logging_config import setup_logging, get_logger, early_setup
# early_setup() already called by logging_config import

# =============================================================================
# Rate Limiting Setup
# =============================================================================
try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    _rate_limiter_enabled = True
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100/minute", "1000/hour"],
        storage_uri=os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )
except ImportError:
    _rate_limiter_enabled = False
    limiter = None

# Initialize Logging - use centralized config
# logging_config.early_setup() already called by import
log = get_logger("presek.api")

app = FastAPI(
    title="Пресек API",
    version=APP_VERSION,
    docs_url="/api/docs" if os.environ.get("ENV") != "production" else None,
    redoc_url="/api/redoc" if os.environ.get("ENV") != "production" else None
)

# Middleware
# Security: Restrict CORS to configured origins. In production, never use "*" with allow_credentials=True
cors_origins = os.environ.get("CORS_ORIGINS", "")
if cors_origins == "*" and os.environ.get("ENV") == "production":
    cors_origins = ["https://presek.live", "https://www.presek.live"]
    log.warning("CORS_ORIGINS was '*', defaulting to presek.live for production security")
else:
    cors_origins = cors_origins.split(",") if cors_origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["*"],
    max_age=600,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

from routes.security import create_security_middleware
create_security_middleware(app)


# =============================================================================
# Security: Input Length Validation Middleware
# =============================================================================

MAX_QUERY_PARAM_LENGTH = 500
MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB


@app.middleware("http")
async def validate_input_length(request: Request, call_next):
    """Validate query parameter and body length to prevent DoS attacks."""
    # Check query parameters
    for name, value in request.query_params.items():
        if len(value) > MAX_QUERY_PARAM_LENGTH:
            return JSONResponse(
                status_code=400,
                content={"error": f"Параметарот '{name}' ја надминува максималната должина од {MAX_QUERY_PARAM_LENGTH} карактери"}
            )
    
    # Check Content-Length for POST/PUT/PATCH requests
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"error": f"Големината на барањето ја надминува максималната дозволена големина од {MAX_BODY_SIZE // (1024*1024)}MB"}
            )
    
    return await call_next(request)


# =============================================================================
# Rate Limit Exceeded Handler
# =============================================================================
if _rate_limiter_enabled:
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        """Return JSON response for rate limit exceeded errors."""
        return JSONResponse(
            status_code=429,
            content={
                "error": "Премногу барања",
                "detail": f"Надминато е ограничувањето за барања: {exc.detail}",
                "status": "rate_limit_exceeded"
            },
            headers={"Retry-After": str(exc.retry_after)}
        )


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Startup Event
@app.on_event("startup")
async def startup_event():
    log.info(f"Пресек API v{APP_VERSION} ({APP_VERSION_LABEL}) starting up...")
    if _rate_limiter_enabled:
        log.info("Rate limiting enabled (slowapi)")
    else:
        log.warning("Rate limiting disabled - slowapi not installed")

# Import and include routers
from routes import home, news, intelligence, profile, stats, system, admin

# Apply rate limiting to routers if enabled
if _rate_limiter_enabled:
    for router in [home.router, news.router, intelligence.router, profile.router, stats.router, system.router, admin.router]:
        router.dependencies.append(limiter)


# Decorator helpers that work with or without slowapi
def exempt_from_rate_limit(func):
    """Decorator that exempts from rate limiting (no-op if slowapi not installed)."""
    if _rate_limiter_enabled:
        return limiter.exempt(func)
    return func


@app.get("/api/health")
@exempt_from_rate_limit
async def health_check():
    """Comprehensive health check for smoke tests and monitoring."""
    import health
    from health import _probe_database, _probe_redis, _freshness_payload, _start_time
    
    db_status = _probe_database()
    redis_status = _probe_redis()
    
    # Get last refresh from Redis
    last_refresh = {}
    try:
        raw = health._get_redis().get(health._REDIS_KEY)
        if raw:
            last_refresh = json.loads(raw)
    except Exception as e:
        log.error(f"Health check error (redis/freshness): {e}")
        pass

    return {
        "status": "healthy" if db_status["ok"] and redis_status["ok"] else "degraded",
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - _start_time),
        "database": db_status,
        "redis": redis_status,
        "freshness": _freshness_payload(last_refresh.get("time")),
        "time": datetime.datetime.now().isoformat()
    }

@app.get("/api/version")
async def version_info():
    return get_full_version_info()

@app.get("/metrics")
@exempt_from_rate_limit
async def metrics():
    """Expose Prometheus metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Proxy for images to avoid CORS/Mixed content issues on client
@app.get("/proxy")
async def image_proxy(
    url: str,
    w: str | None = None,
    cid: str | None = None,
    t: str | None = None,
    cat: str | None = None,
):
    from routes.system import proxy_image
    return await proxy_image(url=url, w=w, cid=cid, t=t, cat=cat)

# Legacy/Helper endpoints
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/img/favicon.ico")

@app.get("/ads.txt")
async def ads_txt():
    return FileResponse("static/ads.txt")

@app.get("/manifest.json")
async def manifest():
    return FileResponse("static/manifest.json")

@app.get("/sw.js")
async def sw_js():
    return FileResponse("sw.js")

@app.get("/static/generated/{filename}")
async def get_generated_image(filename: str):
    return FileResponse(os.path.join("static", "generated", filename))

@app.get("/api/delivery/track/{event_type}")
@exempt_from_rate_limit
async def track_delivery_event(event_type: str, event_id: int, redirect: str = "/briefing"):
    p = await db.async_execute_one("SELECT sync_token, delivery_kind, channel, target, cluster_id FROM delivery_tracking_events WHERE id = %s", (event_id,))
    if p:
        await db.async_execute(
            "INSERT INTO delivery_tracking_events (parent_event_id, event_type, sync_token, delivery_kind, channel, target, cluster_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (event_id, event_type, p['sync_token'], p['delivery_kind'], p['channel'], p['target'], p['cluster_id']),
            fetch=False
        )
    _public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live")
    return RedirectResponse(url=f"{_public_site_url}{redirect}", status_code=302)

# Include routers with /api prefix (for Nginx/Public)
app.include_router(news.router, prefix="/api")
app.include_router(home.router, prefix="/api")
app.include_router(intelligence.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

# Decorator helper for custom rate limits
def custom_rate_limit(limit_str):
    """Factory for rate limit decorators (no-op if slowapi not installed)."""
    if _rate_limiter_enabled:
        return limiter.limit(limit_str)
    return lambda f: f


@app.get("/api/entity-graph/{entity_name}")
@custom_rate_limit("30/minute")
async def entity_graph_lookup(request: Request, entity_name: str):
    """Fetches persistent knowledge about an entity from the local graph."""
    from database import db_manager as db
    
    row = db.execute_one("""
        SELECT bio_summary, importance_score, last_seen, category 
        FROM entity_knowledge WHERE entity_name = %s
    """, (entity_name,))
    if not row:
        row = db.execute_one("""
            SELECT
                COALESCE(metadata->>'bio_summary', '') AS bio_summary,
                total_mentions AS importance_score,
                last_seen,
                COALESCE(type, 'ENTITY') AS category
            FROM knowledge_entities
            WHERE name = %s
        """, (entity_name,))
    
    if not row:
        return {"status": "not_found"}
        
    return {"status": "success", "data": row}

@app.get("/api/research/{cluster_id}")
@custom_rate_limit("10/minute")
async def cluster_research(request: Request, cluster_id: str, q: str):
    """Researches a cluster based on a user query using Gemma 2."""
    from local_analyst import analyst
    from database import db_manager as db
    
    # Get cluster context
    row = db.execute_one("""
        SELECT summary, generated_article 
        FROM cluster_summaries WHERE cluster_id = %s
    """, (cluster_id,))
    
    if not row:
        raise HTTPException(status_code=404, detail="Кластерот не е пронајден")
        
    context = f"{row['summary']}\n{row['generated_article']}"
    res = analyst.research_query(q, context)
    
    return {"status": "success", "answer": res.get('answer'), "suggestions": res.get('suggestions', [])}
