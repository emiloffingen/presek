import asyncio
import datetime
import os
import re
import time

import fastapi
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

if not hasattr(fastapi, "responses"):
    import fastapi.responses

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

from core.api_errors import normalize_http_exception_content, rate_limit_payload
from core.limiter import (
    RateLimitExceeded,
    _rate_limiter_enabled,
    exempt_from_rate_limit,
    limiter,
)
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
    if os.environ.get("PRESEK_SKIP_DB_POOL_INIT") != "1":
        try:
            from core.database import async_db, db_manager

            # Uvicorn prefork workers inherit parent pool state — rebuild both sync pools.
            db_manager._reset_pool()
            await async_db._ensure_pool()
        except Exception as e:
            log.error(f"Failed to initialize async database pools on startup: {e}")

    # Load the local embedding model in the background so the first search isn't slow.
    try:
        from core.embeddings import warm_up

        asyncio.get_running_loop().run_in_executor(None, warm_up)
    except Exception as e:
        log.warning(f"Embedding warm-up skipped: {e}")

    yield

    # Shutdown logic
    log.info("Presek API shutting down, cleaning up resources gracefully...")

    # 1. Close Async Database Pools
    try:
        from core.database import async_db

        if async_db._pool:
            await async_db._pool.close()
            log.info("Async database connection pool closed successfully.")
        async_db._pool = None
        if hasattr(async_db, "_read_pool") and async_db._read_pool:
            await async_db._read_pool.close()
            log.info("Async database read-replica connection pool closed successfully.")
        async_db._read_pool = None
    except Exception as e:
        log.warning(f"Error closing async database pools during shutdown: {e}")

    # 2. Close Sync Database Pools
    try:
        from core.database import db_manager

        if db_manager._pool:
            db_manager._pool.close()
            log.info("Sync database connection pool closed successfully.")
        db_manager._pool = None
        if db_manager._read_pool:
            db_manager._read_pool.close()
            log.info("Sync database read-replica connection pool closed successfully.")
        db_manager._read_pool = None
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
    cors_origins = [
        "https://presek.live",
        "https://www.presek.live",
        "https://presek.rs",
        "https://www.presek.rs",
        "https://presek.mk",
        "https://www.presek.mk",
    ]
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


class APIVersionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/api/v1/"):
                scope["path"] = "/api/" + path[len("/api/v1/") :]
                if "raw_path" in scope:
                    scope["raw_path"] = b"/api/" + path[len("/api/v1/") :].encode("utf-8")
        await self.app(scope, receive, send)


app.add_middleware(APIVersionMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=[
        "Authorization",
        "X-CSRF-Token",
        "X-Admin-Token",
        "X-Sync-Token",
        "Content-Type",
        "Accept",
        "Accept-Language",
    ],
    max_age=600,
)

# Security: Additional security headers are handled in routes/security.py
app.add_middleware(GZipMiddleware, minimum_size=1000)
if _rate_limiter_enabled:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

from routes.security import create_security_middleware

create_security_middleware(app)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    headers = dict(getattr(exc, "headers", None) or {})
    return JSONResponse(
        status_code=exc.status_code,
        content=normalize_http_exception_content(exc.detail),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=normalize_http_exception_content(exc.errors()),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled exception on %s", request.url.path)
    try:
        from core.error_tracking import capture_exception

        capture_exception(exc, {"path": request.url.path, "method": request.method})
    except Exception:
        log.debug("Exception handler fallback")
    return JSONResponse(
        status_code=500,
        content=normalize_http_exception_content("Internal server error"),
    )


@app.get("/api/csrf-token")
@app.get("/api/v1/csrf-token")
def get_csrf_token():
    # Return the same token the cookie carries, so the double-submit check matches.
    from routes.security import set_csrf_cookie

    token = generate_csrf_token()
    response = JSONResponse({"status": "success", "csrf_token": token})
    set_csrf_cookie(response, token)
    return response


# =============================================================================
# Rate Limit Exceeded Handler
# =============================================================================
if _rate_limiter_enabled:

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        """Return JSON response for rate limit exceeded errors."""
        detail = f"Nadminato e ogranicuvanjeto za baranja: {exc.detail}"
        return JSONResponse(
            status_code=429,
            content=rate_limit_payload("Premnogu baranja", detail=detail),
            headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
        )


_AUDIO_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.mp3$")
_UPLOAD_IMAGE_FILENAME_RE = re.compile(r"^art_\d+\.webp$")
_GENERATED_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|svg|webp)$", re.IGNORECASE)
_home_dir = os.environ.get("HOME") or os.path.expanduser("~")
_STATIC_ROOT = os.environ.get("STATIC_ROOT", os.path.join(_home_dir, "presek-runtime", "shared", "static"))
if not os.path.exists(_STATIC_ROOT):
    _STATIC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
_AUDIO_UPLOAD_DIR = os.path.join(_STATIC_ROOT, "uploads", "audio")
_UPLOADS_DIR = os.path.join(_STATIC_ROOT, "uploads")
_GENERATED_DIR = os.path.join(_STATIC_ROOT, "generated")
_LOCAL_METRICS_CLIENTS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})
from prometheus_client import REGISTRY

if "presek_celery_queue_depth" in REGISTRY._names_to_collectors:
    _CELERY_QUEUE_DEPTH = REGISTRY._names_to_collectors["presek_celery_queue_depth"]
else:
    _CELERY_QUEUE_DEPTH = Gauge(
        "presek_celery_queue_depth",
        "Pending Celery tasks by queue",
        ["queue"],
    )

if "presek_celery_failed_tasks_count" in REGISTRY._names_to_collectors:
    _FAILED_TASKS_COUNT = REGISTRY._names_to_collectors["presek_celery_failed_tasks_count"]
else:
    _FAILED_TASKS_COUNT = Gauge(
        "presek_celery_failed_tasks_count",
        "Number of failed celery tasks in the system",
    )

if "presek_postgresql_database_size_mb" in REGISTRY._names_to_collectors:
    _POSTGRESQL_DB_SIZE = REGISTRY._names_to_collectors["presek_postgresql_database_size_mb"]
else:
    _POSTGRESQL_DB_SIZE = Gauge("presek_postgresql_database_size_mb", "Database size in megabytes")

if "presek_articles_total" in REGISTRY._names_to_collectors:
    _ARTICLES_TOTAL = REGISTRY._names_to_collectors["presek_articles_total"]
else:
    _ARTICLES_TOTAL = Gauge("presek_articles_total", "Total number of ingested articles")


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


def _generated_file_path(filename: str) -> str | None:
    if not _GENERATED_FILENAME_RE.fullmatch(filename):
        return None
    generated_root = os.path.abspath(_GENERATED_DIR)
    candidate = os.path.abspath(os.path.join(generated_root, filename))
    try:
        if os.path.commonpath([candidate, generated_root]) != generated_root:
            return None
    except ValueError:
        return None
    return candidate


def _upload_image_file_path(filename: str) -> str | None:
    if not _UPLOAD_IMAGE_FILENAME_RE.fullmatch(filename):
        return None
    upload_root = os.path.abspath(_UPLOADS_DIR)
    candidate = os.path.abspath(os.path.join(upload_root, filename))
    try:
        if os.path.commonpath([candidate, upload_root]) != upload_root:
            return None
    except ValueError:
        return None
    return candidate


_LOCAL_OPS_CLIENTS = _LOCAL_METRICS_CLIENTS | frozenset({"testclient"})


def _is_trusted_ops_client(request: Request) -> bool:
    from routes.common import _has_forwarding_headers

    client_host = str(getattr(getattr(request, "client", None), "host", "") or "")
    if client_host not in _LOCAL_OPS_CLIENTS:
        return False
    # A loopback peer is only a local client when nothing relayed the request:
    # cloudflared and nginx also connect from loopback but add forwarding headers.
    return not _has_forwarding_headers(request)


def _is_local_metrics_client(request: Request) -> bool:
    return _is_trusted_ops_client(request)


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
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{file_size}"},
            )

        start_raw, end_raw = match.groups()
        if start_raw == "" and end_raw == "":
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{file_size}"},
            )

        if start_raw == "":
            suffix_length = int(end_raw)
            if suffix_length <= 0:
                return Response(
                    status_code=416,
                    headers={**headers, "Content-Range": f"bytes */{file_size}"},
                )
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else file_size - 1
            end = min(end, file_size - 1)

        if start >= file_size or start > end:
            return Response(
                status_code=416,
                headers={**headers, "Content-Range": f"bytes */{file_size}"},
            )

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


@app.api_route("/static/uploads/{filename}", methods=["GET", "HEAD"])
async def serve_uploaded_image(filename: str):
    """Serve optimized article images from shared uploads storage."""
    path = _upload_image_file_path(filename)
    if not path or not os.path.isfile(path):
        return JSONResponse(status_code=404, content={"detail": "File not found"})
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})


# Mount static files
app.mount("/static", StaticFiles(directory="static", follow_symlink=False), name="static")


# Import and include routers
from routes import (
    admin,
    home,
    intelligence,
    marketing,
    monitoring,
    news,
    profile,
    stats,
    system,
)


def _safe_rank_cluster_citations(question: str, answer: str, articles, citation_numbers) -> list[dict]:
    try:
        return _rank_cluster_citations(question, answer, articles, citation_numbers)
    except Exception as e:
        log.warning(f"[fastapi cluster_answer] citation ranking failed: {e}", exc_info=True)
        return []


async def _ai_quota_payload() -> dict:
    """Compact per-provider daily AI budget for the status page."""
    try:
        from core.config import AI_ENABLED

        if not AI_ENABLED:
            return {"enabled": False, "providers": {}}
        from core.ai_quota import async_snapshot

        return {"enabled": True, "providers": await async_snapshot()}
    except Exception as exc:  # never let quota reporting break /health
        log.debug("[health] ai quota snapshot failed: %s", exc)
        return {"enabled": None, "providers": {}}


# /api/health runs expensive probes (DB COUNT/size, Redis, Celery queue) and is
# polled frequently by the origin warmup + monitoring, so cache the snapshot
# briefly. Each uvicorn worker keeps its own copy.
_HEALTH_SNAPSHOT_TTL = float(os.environ.get("HEALTH_CACHE_TTL", "30"))
_HEALTH_SNAPSHOT: dict = {"t": 0.0, "data": None}


_HEALTH_REFRESH_LOCK = asyncio.Lock()


def _compute_health_snapshot() -> dict:
    """Blocking health probes (sync DB pool, Redis, Celery broker). Call via a worker thread."""
    import core.health as health
    from core.health import _freshness_payload

    db_status = _probe_database()
    redis_status = _probe_redis()
    db_public = dict(db_status)
    redis_public = dict(redis_status)
    db_public.pop("error", None)
    redis_public.pop("url", None)
    redis_public.pop("error", None)
    redis_public.pop("config", None)

    synthesis_quality = health.get_synthesis_quality_snapshot()
    celery_queue = health._probe_celery_queue()
    operational_status = health.get_operational_status(
        db_status["ok"],
        redis_status["ok"],
        synthesis_quality,
        celery_queue,
    )
    return {
        "status": operational_status,
        "database": db_public,
        "redis": redis_public,
        "synthesis_quality": synthesis_quality,
        "celery_queue": celery_queue,
        "freshness": _freshness_payload(health.load_last_refresh_time()),
    }


@app.get("/api/health")
@exempt_from_rate_limit
async def health_check(request: Request):
    """Comprehensive health check for smoke tests and monitoring."""
    from core.health import _start_time

    snap = _HEALTH_SNAPSHOT["data"]
    if snap is None or (time.time() - _HEALTH_SNAPSHOT["t"]) >= _HEALTH_SNAPSHOT_TTL:
        if snap is not None and _HEALTH_REFRESH_LOCK.locked():
            # Another request is already refreshing; answer from the previous snapshot.
            pass
        else:
            async with _HEALTH_REFRESH_LOCK:
                snap = _HEALTH_SNAPSHOT["data"]
                if snap is None or (time.time() - _HEALTH_SNAPSHOT["t"]) >= _HEALTH_SNAPSHOT_TTL:
                    # The probes use the synchronous DB pool, Redis and the Celery broker.
                    # Run on a worker thread: blocking the event loop here froze the whole API
                    # whenever the small PgBouncer pool was busy (see PR description).
                    snap = await asyncio.to_thread(_compute_health_snapshot)
                    snap["ai"] = await _ai_quota_payload()
                    _HEALTH_SNAPSHOT["data"] = snap
                    _HEALTH_SNAPSHOT["t"] = time.time()

    payload = {
        "status": snap["status"],
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - _start_time),
        "database": snap["database"],
        "redis": snap["redis"],
        "time": datetime.datetime.now().isoformat(),
    }

    if _is_trusted_ops_client(request):
        cq = snap["celery_queue"]
        celery_public = {
            "celery_depth": cq.get("celery_depth", 0),
            "total_depth": cq.get("total_depth", 0),
            "warn_depth": cq.get("warn_depth", 100),
            "critical_depth": cq.get("critical_depth", 500),
            "degraded": cq.get("degraded", False),
            "queues": cq.get("queues", {}),
        }
        payload["freshness"] = snap["freshness"]
        payload["celery_queue"] = celery_public
        payload["synthesis_quality"] = snap["synthesis_quality"]
        payload["ai"] = snap["ai"]

    return payload


if hasattr(app, "head"):

    @app.head("/api/health")
    @exempt_from_rate_limit
    async def health_check_head():
        """Allow HEAD-based uptime probes to validate that the health route exists."""
        return Response(status_code=200)


@app.get("/api/version")
async def version_info():
    return get_full_version_info()


if "presek_db_pool_connections_num" in REGISTRY._names_to_collectors:
    _DB_POOL_CONNECTIONS_NUM = REGISTRY._names_to_collectors["presek_db_pool_connections_num"]
else:
    _DB_POOL_CONNECTIONS_NUM = Gauge(
        "presek_db_pool_connections_num",
        "Current number of connections in the pool",
        ["pool_type", "role"],
    )

if "presek_db_pool_available" in REGISTRY._names_to_collectors:
    _DB_POOL_AVAILABLE = REGISTRY._names_to_collectors["presek_db_pool_available"]
else:
    _DB_POOL_AVAILABLE = Gauge(
        "presek_db_pool_available",
        "Number of available (idle) connections in the pool",
        ["pool_type", "role"],
    )

if "presek_db_pool_waiting" in REGISTRY._names_to_collectors:
    _DB_POOL_WAITING = REGISTRY._names_to_collectors["presek_db_pool_waiting"]
else:
    _DB_POOL_WAITING = Gauge(
        "presek_db_pool_waiting",
        "Number of requests currently waiting for a connection",
        ["pool_type", "role"],
    )


def update_db_pool_metrics():
    """Update Prometheus Gauges with active database connection pool stats."""
    from core.database import async_db, db_manager

    def collect_pool_stats(pool, pool_type: str, role: str):
        if pool is None:
            return
        try:
            stats = pool.get_stats()
            _DB_POOL_CONNECTIONS_NUM.labels(pool_type=pool_type, role=role).set(stats.get("connections_num", 0))
            _DB_POOL_AVAILABLE.labels(pool_type=pool_type, role=role).set(stats.get("pool_available", 0))
            _DB_POOL_WAITING.labels(pool_type=pool_type, role=role).set(stats.get("requests_waiting", 0))
        except Exception as e:
            log.warning(f"Failed to collect database pool stats for {pool_type} {role}: {e}")

    collect_pool_stats(getattr(db_manager, "_pool", None), "sync", "primary")
    collect_pool_stats(getattr(db_manager, "_read_pool", None), "sync", "replica")
    collect_pool_stats(getattr(async_db, "_pool", None), "async", "primary")
    collect_pool_stats(getattr(async_db, "_read_pool", None), "async", "replica")


@app.get("/metrics")
@app.get("/api/metrics")
@exempt_from_rate_limit
async def metrics(request: Request):
    """Expose Prometheus metrics to local scrapers only."""
    if not _is_local_metrics_client(request):
        return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    try:
        from core.queue_status import get_all_queue_depths

        for queue, depth in get_all_queue_depths().items():
            _CELERY_QUEUE_DEPTH.labels(queue=queue).set(depth)
    except Exception as exc:
        log.warning("Failed to refresh Celery queue metrics: %s", exc)

    try:
        update_db_pool_metrics()
    except Exception as exc:
        log.warning("Failed to refresh database pool metrics: %s", exc)

    try:
        from core.database import db_manager

        # 1. Fetch database size
        size_mb = db_manager.get_db_size()
        _POSTGRESQL_DB_SIZE.set(size_mb)

        # 2. Fetch failed tasks count
        failed_tasks_count_row = db_manager.execute("SELECT COUNT(*) as count FROM failed_tasks")
        failed_tasks_count = failed_tasks_count_row[0]["count"] if failed_tasks_count_row else 0
        _FAILED_TASKS_COUNT.set(failed_tasks_count)

        # 3. Fetch total articles count
        articles_total_row = db_manager.execute("SELECT COUNT(*) as count FROM articles")
        articles_total = articles_total_row[0]["count"] if articles_total_row else 0
        _ARTICLES_TOTAL.set(articles_total)
    except Exception as exc:
        log.warning("Failed to refresh custom operation metrics: %s", exc)

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
    lang: str | None = None,
):
    from routes.system import proxy_image

    return await proxy_image(url=url, w=w, cid=cid, t=t, cat=cat, theme=theme, lang=lang)


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
    path = _generated_file_path(filename)
    if not path or not os.path.isfile(path):
        return JSONResponse(status_code=404, content={"detail": "File not found"})
    return FileResponse(path)


@app.get("/api/delivery/track/{event_type}")
@exempt_from_rate_limit
async def track_delivery_event(
    event_type: str,
    event_id: int,
    token: str,
    redirect: str = "/briefing",
):
    from core.signed_tokens import (
        ALLOWED_DELIVERY_EVENT_TYPES,
        parse_delivery_track_token,
    )
    from routes.common import _safe_tracking_redirect_path

    clean_type = str(event_type or "").strip().lower()
    if clean_type not in ALLOWED_DELIVERY_EVENT_TYPES:
        return JSONResponse(status_code=400, content={"detail": "Invalid event type"})

    parsed = parse_delivery_track_token(token)
    if not parsed:
        return JSONResponse(status_code=400, content={"detail": "Invalid tracking token"})

    parsed_event_id, parsed_type, parsed_redirect = parsed
    if parsed_event_id != event_id or parsed_type != clean_type:
        return JSONResponse(status_code=400, content={"detail": "Invalid tracking token"})

    p = await db.async_execute_one(
        "SELECT sync_token, delivery_kind, channel, target, cluster_id FROM delivery_tracking_events WHERE id = %s",
        (event_id,),
    )
    if p:
        await db.async_execute(
            "INSERT INTO delivery_tracking_events (parent_event_id, event_type, sync_token, delivery_kind, channel, target, cluster_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                event_id,
                clean_type,
                p["sync_token"],
                p["delivery_kind"],
                p["channel"],
                p["target"],
                p["cluster_id"],
            ),
            fetch=False,
        )
    _public_site_url = os.environ.get("PUBLIC_SITE_URL", "https://presek.live")
    redirect = _safe_tracking_redirect_path(parsed_redirect or redirect)
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

        task = celery_app.send_task("tasks.extractive.recluster_recent_articles_task", args=[hours, limit])

        return {
            "status": "success",
            "task_id": str(task.id),
            "message": f"Triggered reclustering for last {hours} hours, limit {limit} articles",
        }
    except Exception as e:
        log.error(f"Failed to trigger reclustering: {e}")
        raise HTTPException(status_code=503, detail="Failed to trigger reclustering") from e


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

        task = celery_app.send_task("tasks.extractive.discover_storylines_task")

        return {
            "status": "success",
            "task_id": str(task.id),
            "message": "Triggered storyline discovery",
        }
    except Exception as e:
        log.error(f"Failed to trigger storyline discovery: {e}")
        raise HTTPException(status_code=503, detail="Failed to trigger storyline discovery") from e


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
        return {"status": "error", "error": "Failed to get clustering status"}


# Include routers with /api prefix
app.include_router(news.router, prefix="/api")
app.include_router(home.router, prefix="/api")
app.include_router(intelligence.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(marketing.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
