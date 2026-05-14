import os
import json
import datetime
import time
from fastapi import FastAPI, Request
from fastapi.responses import Response
import fastapi

if not hasattr(fastapi, "responses"):
    import fastapi.responses
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from limiter import (
    _rate_limiter_enabled,
    limiter,
    RateLimitExceeded,
    exempt_from_rate_limit,
)

if _rate_limiter_enabled:
    from slowapi.middleware import SlowAPIMiddleware

from database import db_manager as db
from version import APP_VERSION, APP_VERSION_LABEL, get_full_version_info

# Initialize logging early (before other imports)
from logging_config import get_logger

# early_setup() already called by logging_config import

# Initialize Logging - use centralized config
# logging_config.early_setup() already called by import
log = get_logger("presek.api")

app = FastAPI(
    title="Presek API",
    version=APP_VERSION,
    docs_url="/api/docs" if os.environ.get("ENV") != "production" else None,
    redoc_url="/api/redoc" if os.environ.get("ENV") != "production" else None,
)
from health import _probe_database, _probe_redis
from api_helpers import (
    rank_cluster_citations as _rank_cluster_citations,
)

# Middleware
# Security: Restrict CORS to configured origins. In production, never use "*" with allow_credentials=True
cors_origins = os.environ.get("CORS_ORIGINS", "")
if cors_origins == "*" and os.environ.get("ENV") == "production":
    cors_origins = ["https://presek.live", "https://www.presek.live", "https://presek.mk", "https://www.presek.mk"]
    log.warning(
        "CORS_ORIGINS was '*', defaulting to presek.live and presek.mk for production security"
    )
elif cors_origins == "*":
    # In development, still avoid wildcard - use explicit localhost origins
    cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5001", "http://127.0.0.1:5001", "http://localhost:3001", "http://127.0.0.1:3001"]
    log.warning(
        "CORS_ORIGINS set to '*' in development - using explicit localhost origins instead"
    )
else:
    cors_origins = cors_origins.split(",") if cors_origins else ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5001", "http://127.0.0.1:5001", "http://localhost:3001", "http://127.0.0.1:3001"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["*"],
    max_age=600,
)

# Security: Additional security headers are handled in routes/security.py
app.add_middleware(GZipMiddleware, minimum_size=1000)
if _rate_limiter_enabled:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

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
                content={
                    "error": f"Parametarot '{name}' ja nadminuva maksimalnata dolzina od {MAX_QUERY_PARAM_LENGTH} karakteri"
                },
            )

    # Check Content-Length for POST/PUT/PATCH requests
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_SIZE:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": f"Goleminata na baranjeto me nadminuva maksimalnata dozvolena golemina od {MAX_BODY_SIZE // (1024*1024)}MB"
                        },
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Nevaliden Content-Length naslov"},
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
                "error": "Premnogu baranja",
                "detail": f"Nadminato e ogranicuvanjeto za baranja: {exc.detail}",
                "status": "rate_limit_exceeded",
            },
            headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
        )


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# Startup Event
@app.on_event("startup")
async def startup_event():
    log.info(f"Presek API v{APP_VERSION} ({APP_VERSION_LABEL}) starting up...")
    if _rate_limiter_enabled:
        log.info("Rate limiting enabled (slowapi)")
    else:
        log.warning("Rate limiting disabled - slowapi not installed")


# Import and include routers
from routes import home, news, intelligence, profile, stats, system, admin


def _safe_rank_cluster_citations(
    question: str, answer: str, articles, citation_numbers
) -> list[dict]:
    try:
        return _rank_cluster_citations(question, answer, articles, citation_numbers)
    except Exception as e:
        log.warning(
            f"[fastapi cluster_answer] citation ranking failed: {e}", exc_info=True
        )
        return []


@app.get("/api/health")
@exempt_from_rate_limit
async def health_check():
    """Comprehensive health check for smoke tests and monitoring."""
    import health
    from health import _freshness_payload, _start_time

    db_status = _probe_database()
    redis_status = _probe_redis()
    db_public = dict(db_status)
    redis_public = dict(redis_status)
    db_public.pop("error", None)
    redis_public.pop("url", None)
    redis_public.pop("error", None)
    redis_public.pop("config", None)

    # Get last refresh from Redis
    last_refresh = {}
    try:
        raw = health._get_redis().get(health._REDIS_KEY)
        if raw:
            last_refresh = json.loads(raw)
    except Exception as e:
        log.error(f"Health check error (redis/freshness): {e}")

    return {
        "status": "healthy" if db_status["ok"] and redis_status["ok"] else "degraded",
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - _start_time),
        "database": db_public,
        "redis": redis_public,
        "freshness": _freshness_payload(last_refresh.get("time")),
        "time": datetime.datetime.now().isoformat(),
    }


if hasattr(app, "head"):

    @app.head("/api/health")
    @exempt_from_rate_limit
    async def health_check_head():
        """Allow HEAD-based uptime probes to validate that the health route exists."""
        return Response(status_code=200)


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
async def track_delivery_event(
    event_type: str, event_id: int, redirect: str = "/briefing"
):
    from routes.common import _safe_tracking_redirect_path

    p = await db.async_execute_one(
        "SELECT sync_token, delivery_kind, channel, target, cluster_id FROM delivery_tracking_events WHERE id = %s",
        (event_id,),
    )
    if p:
        await db.async_execute(
            "INSERT INTO delivery_tracking_events (parent_event_id, event_type, sync_token, delivery_kind, channel, target, cluster_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                event_id,
                event_type,
                p["sync_token"],
                p["delivery_kind"],
                p["channel"],
                p["target"],
                p["cluster_id"],
            ),
            fetch=False,
        )
    _public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live")
    redirect = _safe_tracking_redirect_path(redirect)
    return RedirectResponse(url=f"{_public_site_url}{redirect}", status_code=302)


# API Versioning - support both /api (legacy) and /api/v1 (versioned)
# For new development, use /api/v1. Legacy /api routes are maintained for backward compatibility.
API_VERSION = "v1"

# Include routers with /api prefix (for Nginx/Public, legacy support)
app.include_router(news.router, prefix="/api")
app.include_router(home.router, prefix="/api")
app.include_router(intelligence.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

# Also include v1-prefixed routers for API versioning
app.include_router(news.router, prefix=f"/api/{API_VERSION}")
app.include_router(home.router, prefix=f"/api/{API_VERSION}")
app.include_router(intelligence.router, prefix=f"/api/{API_VERSION}")
app.include_router(profile.router, prefix=f"/api/{API_VERSION}")
app.include_router(stats.router, prefix=f"/api/{API_VERSION}")
app.include_router(system.router, prefix=f"/api/{API_VERSION}")
app.include_router(admin.router, prefix=f"/api/{API_VERSION}")
