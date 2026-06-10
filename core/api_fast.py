import datetime
import json
import os
import re
import time

import fastapi
from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response

if not hasattr(fastapi, "responses"):
    import fastapi.responses

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core.limiter import RateLimitExceeded, _rate_limiter_enabled, exempt_from_rate_limit, limiter
from routes.security import generate_csrf_token, verify_csrf_token

if _rate_limiter_enabled:
    from slowapi.middleware import SlowAPIMiddleware

from core.database import db_manager as db
from core.error_tracking import configure_error_tracking

# Initialize logging early (before other imports)
from core.logging_config import get_logger
from core.version import APP_VERSION, APP_VERSION_LABEL, get_full_version_info

# early_setup() already called by logging_config import
# Initialize error tracking
configure_error_tracking()

from contextlib import asynccontextmanager

# Initialize Logging - use centralized config
# logging_config.early_setup() already called by import
log = get_logger("presek.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    log.info(f"Presek API v{APP_VERSION} ({APP_VERSION_LABEL}) starting up...")
    if _rate_limiter_enabled:
        log.info("Rate limiting enabled (slowapi)")
    else:
        log.warning("Rate limiting disabled - slowapi not installed")

    # Warm up async database pools on startup
    try:
        from core.database import async_db
        await async_db._ensure_pool()
    except Exception as e:
        log.error(f"Failed to initialize async database pools on startup: {e}")

    yield

    # Shutdown logic
    log.info("Presek API shutting down, cleaning up resources gracefully...")

    # 1. Close Async Database Pools
    try:
        from core.database import async_db
        if async_db._pool:
            await async_db._pool.close()
            log.info("Async database connection pool closed successfully.")
        if hasattr(async_db, "_read_pool") and async_db._read_pool:
            await async_db._read_pool.close()
            log.info("Async database read-replica connection pool closed successfully.")
    except Exception as e:
        log.warning(f"Error closing async database pools during shutdown: {e}")

    # 2. Close Sync Database Pools
    try:
        from core.database import db_manager
        if db_manager._pool:
            db_manager._pool.close()
            log.info("Sync database connection pool closed successfully.")
        if db_manager._read_pool:
            db_manager._read_pool.close()
            log.info("Sync database read-replica connection pool closed successfully.")
    except Exception as e:
        log.warning(f"Error closing sync database pools during shutdown: {e}")

    # 3. Disconnect Redis Client
    try:
        from utils import redis_client
        if redis_client:
            redis_client.close()
            log.info("Redis cache client disconnected successfully.")
    except Exception as e:
        log.warning(f"Error disconnecting Redis client during shutdown: {e}")

    # 4. Shutdown Embedding Thread Pool and Unload Local AI Model
    try:
        from core.embeddings import shutdown_embedding_executor
        shutdown_embedding_executor()
    except Exception as e:
        log.warning(f"Error shutting down embedding thread pool during shutdown: {e}")


app = FastAPI(
    title="Presek API",
    version=APP_VERSION,
    docs_url="/api/docs" if os.environ.get("ENV") != "production" else None,
    redoc_url="/api/redoc" if os.environ.get("ENV") != "production" else None,
    lifespan=lifespan,
)
from core.api_helpers import rank_cluster_citations as _rank_cluster_citations
from core.health import _probe_database, _probe_redis

# Middleware
# Security: Restrict CORS to configured origins. In production, never use "*" with allow_credentials=True
cors_origins = os.environ.get("CORS_ORIGINS", "")
if cors_origins == "*" and os.environ.get("ENV") == "production":
    cors_origins = ["https://presek.live", "https://www.presek.live", "https://presek.rs", "https://www.presek.rs", "https://presek.mk", "https://www.presek.mk"]
    log.warning("CORS_ORIGINS was '*', defaulting to presek.live, presek.rs, and presek.mk for production security")
elif cors_origins == "*":
    # In development, still avoid wildcard - use explicit localhost origins
    cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5001",
        "http://127.0.0.1:5001",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    log.warning("CORS_ORIGINS set to '*' in development - using explicit localhost origins instead")
else:
    cors_origins = (
        cors_origins.split(",")
        if cors_origins
        else [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5001",
            "http://127.0.0.1:5001",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]
    )

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


@app.get("/api/csrf-token")
@app.get("/api/v1/csrf-token")
def get_csrf_token():
    return {"status": "success", "csrf_token": generate_csrf_token()}


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


_AUDIO_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.mp3$")
_STATIC_ROOT = "/home/emiloffingen/presek-runtime/shared/static"
if not os.path.exists(_STATIC_ROOT):
    _STATIC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
_AUDIO_UPLOAD_DIR = os.path.join(_STATIC_ROOT, "uploads", "audio")


def _audio_file_path(filename: str) -> str | None:
    if not _AUDIO_FILENAME_RE.fullmatch(filename):
        return None
    candidate = os.path.abspath(os.path.join(_AUDIO_UPLOAD_DIR, filename))
    try:
        if os.path.commonpath([candidate, os.path.abspath(_AUDIO_UPLOAD_DIR)]) != os.path.abspath(_AUDIO_UPLOAD_DIR):
            return None
    except ValueError:
        return None
    return candidate


def _iter_file_range(path: str, start: int, end: int, chunk_size: int = 64 * 1024):
    with open(path, "rb") as handle:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@app.api_route("/static/uploads/audio/{filename}", methods=["GET", "HEAD"])
async def serve_uploaded_audio(filename: str, request: Request):
    """Serve generated MP3s with byte-range support for browser audio controls."""
    path = _audio_file_path(filename)
    if not path or not os.path.exists(path) or not os.path.isfile(path):
        return JSONResponse(status_code=404, content={"detail": "Audio file not found"})

    file_size = os.path.getsize(path)
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=3600",
        "Content-Encoding": "identity",
    }
    range_header = request.headers.get("range")

    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{file_size}"})

        start_raw, end_raw = match.groups()
        if start_raw == "" and end_raw == "":
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{file_size}"})

        if start_raw == "":
            suffix_length = int(end_raw)
            if suffix_length <= 0:
                return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{file_size}"})
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else file_size - 1
            end = min(end, file_size - 1)

        if start >= file_size or start > end:
            return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{file_size}"})

        content_length = end - start + 1
        partial_headers = {
            **headers,
            "Content-Length": str(content_length),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
        }
        if request.method == "HEAD":
            return Response(status_code=206, headers=partial_headers, media_type="audio/mpeg")
        return StreamingResponse(
            _iter_file_range(path, start, end),
            status_code=206,
            headers=partial_headers,
            media_type="audio/mpeg",
        )

    full_headers = {**headers, "Content-Length": str(file_size)}
    if request.method == "HEAD":
        return Response(headers=full_headers, media_type="audio/mpeg")
    return StreamingResponse(
        _iter_file_range(path, 0, file_size - 1),
        headers=full_headers,
        media_type="audio/mpeg",
    )


# Mount static files
app.mount("/static", StaticFiles(directory="static", follow_symlink=True), name="static")





# Import and include routers
from routes import admin, home, intelligence, news, profile, stats, system


def _safe_rank_cluster_citations(question: str, answer: str, articles, citation_numbers) -> list[dict]:
    try:
        return _rank_cluster_citations(question, answer, articles, citation_numbers)
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] citation ranking failed: {e}", exc_info=True)
        return []


@app.get("/api/health")
@exempt_from_rate_limit
async def health_check():
    """Comprehensive health check for smoke tests and monitoring."""
    import core.health as health
    from core.health import _freshness_payload, _start_time

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

    synthesis_quality = health.get_synthesis_quality_snapshot()
    celery_queue = health._probe_celery_queue()
    celery_public = {
        "celery_depth": celery_queue.get("celery_depth", 0),
        "total_depth": celery_queue.get("total_depth", 0),
        "warn_depth": celery_queue.get("warn_depth", 100),
        "critical_depth": celery_queue.get("critical_depth", 500),
        "degraded": celery_queue.get("degraded", False),
        "queues": celery_queue.get("queues", {}),
    }
    operational_status = health.get_operational_status(
        db_status["ok"],
        redis_status["ok"],
        synthesis_quality,
        celery_queue,
    )

    return {
        "status": operational_status,
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - _start_time),
        "database": db_public,
        "redis": redis_public,
        "freshness": _freshness_payload(last_refresh.get("time")),
        "celery_queue": celery_public,
        "synthesis_quality": synthesis_quality,
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
    url: str = "",
    w: str | None = None,
    cid: str | None = None,
    t: str | None = None,
    cat: str | None = None,
    theme: str | None = None,
):
    from routes.system import proxy_image

    return await proxy_image(url=url, w=w, cid=cid, t=t, cat=cat, theme=theme)


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


# Clustering Control Endpoints - Manual triggers for debugging/emergency use
@app.post("/api/admin/trigger-reclustering")
def trigger_reclustering(
    hours: int = 6,
    limit: int = 500,
    authorized: str = Depends(admin.verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """
    Manually trigger reclustering of recent articles.
    Used when automatic clustering fails or for emergency recovery.
    """
    try:
        from core.celery_app import celery_app

        task = celery_app.send_task("tasks.intelligence.recluster_recent_articles_task", args=[hours, limit])

        return {
            "status": "success",
            "task_id": str(task.id),
            "message": f"Triggered reclustering for last {hours} hours, limit {limit} articles",
        }
    except Exception as e:
        log.error(f"Failed to trigger reclustering: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/admin/trigger-storyline-discovery")
def trigger_storyline_discovery(
    authorized: str = Depends(admin.verify_admin),
    csrf_valid: bool = Depends(verify_csrf_token),
):
    """
    Manually trigger storyline discovery.
    Used when storylines aren't being created automatically.
    """
    try:
        from core.celery_app import celery_app

        task = celery_app.send_task("tasks.intelligence.discover_storylines_task")

        return {"status": "success", "task_id": str(task.id), "message": "Triggered storyline discovery"}
    except Exception as e:
        log.error(f"Failed to trigger storyline discovery: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/admin/clustering-status")
def get_clustering_status(authorized: str = Depends(admin.verify_admin)):
    """
    Get current clustering system status.
    """
    try:
        # Check recent articles
        recent_articles = db.execute(
            "SELECT COUNT(*) as count FROM articles WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )[0]["count"]

        # Check articles with cluster IDs
        clustered_articles = db.execute(
            "SELECT COUNT(*) as count FROM articles WHERE cluster_id IS NOT NULL AND created_at >= NOW() - INTERVAL '24 hours'"
        )[0]["count"]

        # Check storylines
        storylines = db.execute(
            "SELECT COUNT(*) as count FROM storylines_v2 WHERE created_at >= NOW() - INTERVAL '24 hours'"
        )[0]["count"]

        # Check clusters in storylines
        clusters_in_storylines = db.execute("SELECT COUNT(*) as count FROM storyline_clusters_v2")[0]["count"]

        return {
            "status": "success",
            "stats": {
                "recent_articles_24h": recent_articles,
                "clustered_articles_24h": clustered_articles,
                "storylines_24h": storylines,
                "clusters_in_storylines_total": clusters_in_storylines,
                "clustering_rate": (
                    round(clustered_articles / max(recent_articles, 1) * 100, 1) if recent_articles > 0 else 0
                ),
            },
            "health": {
                "articles_ingested": recent_articles > 0,
                "articles_clustered": clustered_articles > 0,
                "storylines_created": storylines > 0,
                "clusters_available": clusters_in_storylines > 0,
                "overall_healthy": storylines > 0 and clusters_in_storylines > 0,
            },
        }
    except Exception as e:
        log.error(f"Failed to get clustering status: {e}")
        return {"status": "error", "error": str(e)}


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
