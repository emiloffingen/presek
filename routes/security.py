import importlib
import logging
import os
import re
import secrets
import hmac
import hashlib
import time
from typing import Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.config import API_MAX_Q_LEN

log = logging.getLogger("presek")


def _raise_http_error(status_code: int, detail: str):
    try:
        fastapi_mod = importlib.import_module("fastapi")
        exc_cls = getattr(fastapi_mod, "HTTPException", HTTPException)
    except Exception as e:
        log.debug(f"Failed to import fastapi: {e}")
        exc_cls = HTTPException
    raise exc_cls(status_code=status_code, detail=detail)


# =============================================================================
# CSRF Protection System
# =============================================================================

# Initialize CSRF secret - use environment variable or generate a stable one
_CSRF_SECRET_FILE = "/tmp/presek_csrf_secret.txt"
if os.environ.get("CSRF_TOKEN_SECRET"):
    CSRF_TOKEN_SECRET = os.environ.get("CSRF_TOKEN_SECRET")
elif os.environ.get("ENV") == "production":
    raise RuntimeError("CSRF_TOKEN_SECRET must be set in production")
elif os.path.exists(_CSRF_SECRET_FILE):
    with open(_CSRF_SECRET_FILE, "r") as f:
        CSRF_TOKEN_SECRET = f.read().strip()
else:
    CSRF_TOKEN_SECRET = secrets.token_urlsafe(32)
    try:
        with open(_CSRF_SECRET_FILE, "w") as f:
            f.write(CSRF_TOKEN_SECRET)
    except Exception:
        pass  # If we can't write the file, just use the in-memory secret

CSRF_TOKEN_EXPIRY = 3600  # 1 hour


def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    timestamp = str(int(time.time()))
    message = f"{timestamp}:{CSRF_TOKEN_SECRET}"
    signature = hmac.new(CSRF_TOKEN_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return f"{timestamp}:{signature}"


def validate_csrf_token(token: str) -> bool:
    """Validate a CSRF token."""
    if not token or ":" not in token:
        return False
    
    try:
        timestamp_str, signature = token.split(":", 1)
        timestamp = int(timestamp_str)
        
        # Check if token is expired
        if int(time.time()) - timestamp > CSRF_TOKEN_EXPIRY:
            return False
        
        # Reconstruct and validate signature
        message = f"{timestamp}:{CSRF_TOKEN_SECRET}"
        expected_signature = hmac.new(
            CSRF_TOKEN_SECRET.encode(), 
            message.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False


async def verify_csrf_token(request: Request):
    """Dependency for CSRF token validation."""
    # Allow GET, HEAD, OPTIONS requests
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    
    # Check for CSRF token in header or form data
    csrf_token = request.headers.get("X-CSRF-Token")
    
    if not csrf_token:
        try:
            form_data = await request.form()
            csrf_token = form_data.get("csrf_token")
        except Exception:
            pass
    
    if not validate_csrf_token(csrf_token):
        raise HTTPException(
            status_code=403,
            detail="Nevaliden CSRF token"
        )
    
    return True



# Security Headers Middleware
# =============================================================================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate a unique nonce for this request for CSP
        csp_nonce = secrets.token_hex(16)

        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
        # HSTS: Only enable preload in production with HTTPS
        # In development, use shorter max-age without preload to avoid breaking local dev
        if os.environ.get("ENV") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        else:
            response.headers["Strict-Transport-Security"] = "max-age=300; includeSubDomains"

        # Content Security Policy with nonce-based approach
        # Nonce allows inline scripts/styles that include the nonce attribute
        # External domains must be carefully reviewed - third-party scripts require
        # either nonce support or explicit trust
        # See: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
        content_type = response.headers.get("content-type", "")
        if "image/svg+xml" in content_type:
            # Special secure CSP for SVG images to allow rendering stylesheet styles
            # while blocking all script execution.
            csp = "default-src 'none'; style-src 'unsafe-inline';"
        else:
            csp = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{csp_nonce}' https://cdn.jsdelivr.net; "
                f"style-src 'self' 'nonce-{csp_nonce}' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https: blob: https://www.google-analytics.com https://www.googletagmanager.com; "
                "connect-src 'self' https: https://www.google-analytics.com https://analytics.google.com wss:; "
                "frame-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "object-src 'none'; "
                "media-src 'self' data: https:; "
                "worker-src 'self' blob:"
            )
        response.headers["Content-Security-Policy"] = csp

        # Set nonce in a cookie so frontend can access it for inline styles/scripts
        # In production with HTTPS, secure=True prevents MITM attacks
        # In development without HTTPS, secure=False is required
        is_production = os.environ.get("ENV") == "production"
        response.set_cookie(
            key="csp-nonce",
            value=csp_nonce,
            httponly=True,
            secure=is_production,
            samesite="lax",
            max_age=300,  # 5 minutes - match typical page load time
        )

        # Add CSRF token cookie for frontend use
        csrf_token = generate_csrf_token()
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,  # Must be accessible to JavaScript
            secure=is_production,
            samesite="lax",
            max_age=CSRF_TOKEN_EXPIRY,
        )


        # Permissions Policy
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        # Cross-Origin policies (COEP only on HTML — require-corp breaks third-party API assets)
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if "text/html" in content_type:
            response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

        # Additional security headers
        response.headers["X-DNS-Prefetch-Control"] = "off"

        return response


# =============================================================================
# Security Headers Middleware
# =============================================================================


# =============================================================================
# Input Validation Helpers
# =============================================================================

CLUSTER_ID_PATTERN = re.compile(r"^[a-f0-9\-]{6,64}$")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def validate_cluster_id(cluster_id: str, param_name: str = "cluster_id") -> str:
    """Validate cluster ID format (hex string, 6-64 chars)."""
    if not cluster_id:
        raise HTTPException(status_code=400, detail=f"{param_name} e zadolzitelno")
    if not isinstance(cluster_id, str):
        raise HTTPException(status_code=400, detail=f"{param_name} mora da bide tekst")
    if not CLUSTER_ID_PATTERN.match(cluster_id):
        _raise_http_error(400, f"Invalid {param_name}. Must be 6-64 character hexadecimal string.")
    return cluster_id


def validate_date(date_str: str, param_name: str = "date") -> str:
    """Validate date format (YYYY-MM-DD)."""
    if not date_str:
        raise HTTPException(status_code=400, detail=f"{param_name} e zadolzitelno")
    if not DATE_PATTERN.match(date_str):
        _raise_http_error(400, f"Invalid {param_name}. Must be in YYYY-MM-DD format.")
    return date_str


def validate_email(email: str, param_name: str = "email") -> str:
    """Validate email format."""
    if not email:
        raise HTTPException(status_code=400, detail=f"{param_name} e zadolzitelno")
    email = email.strip().lower()
    if len(email) > 254:
        raise HTTPException(status_code=400, detail=f"{param_name} e predolgo")
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail=f"Nevalidno {param_name}")
    return email


def validate_string_param(
    value: str,
    param_name: str,
    max_length: int = 200,
    min_length: int = 0,
    allow_empty: bool = True,
) -> str:
    """Validate a string parameter with length constraints."""
    if value is None:
        if allow_empty:
            return ""
        raise HTTPException(status_code=400, detail=f"{param_name} e zadolzitelno")

    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{param_name} mora da bide tekst")

    value = value.strip()
    if not allow_empty and not value:
        raise HTTPException(status_code=400, detail=f"{param_name} e zadolzitelno")

    if len(value) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"{param_name} ja nadminuva maksimalnata dolzina od {max_length}",
        )

    if len(value) < min_length and value:
        raise HTTPException(
            status_code=400,
            detail=f"{param_name} mora da ima barem {min_length} karakteri",
        )

    return value


def validate_list_param(items, param_name: str, max_items: int = 20, max_item_length: int = 100) -> list:
    """Validate a list parameter."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail=f"{param_name} mora da bide lista")
    if len(items) > max_items:
        raise HTTPException(
            status_code=400,
            detail=f"{param_name} go nadminuva maksimumot od {max_items} elementi",
        )
    result = []
    for item in items:
        if not isinstance(item, str):
            raise HTTPException(
                status_code=400,
                detail=f"Site elementi vo {param_name} mora da bidat tekst",
            )
        cleaned = item.strip()
        if len(cleaned) > max_item_length:
            raise HTTPException(
                status_code=400,
                detail=f"Elementite vo {param_name} ja nadminuvaat maksimalnata dolzina od {max_item_length}",
            )
        if cleaned:
            result.append(cleaned)
    return result


# =============================================================================
# Authentication Helpers
# =============================================================================


def verify_sync_token(request: Request) -> str:
    """Extract and validate sync token from request."""
    from .common import _extract_sync_token, _validate_sync_token_value

    return _validate_sync_token_value(_extract_sync_token(request))


# =============================================================================
# Security Headers Middleware
# =============================================================================


# =============================================================================
# Request Size Limiting Middleware
# =============================================================================

MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_QUERY_PARAM_LENGTH = API_MAX_Q_LEN
MAX_HEADER_VALUE_LENGTH = 2000


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request sizes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check declared body size before reading the request downstream.
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BODY_SIZE:
                    _raise_http_error(413, "Request body exceeds maximum size")
            except ValueError:
                raise HTTPException(status_code=400, detail="Nevaliden Content-Length naslov")

        # Check query parameters
        for key, value in request.query_params.items():
            if len(value) > MAX_QUERY_PARAM_LENGTH:
                _raise_http_error(400, f"Query parameter '{key}' exceeds maximum length")

        # Check headers
        for key, value in request.headers.items():
            if isinstance(value, str) and len(value) > MAX_HEADER_VALUE_LENGTH:
                _raise_http_error(400, f"Header '{key}' exceeds maximum length")

        response = await call_next(request)
        return response


# =============================================================================
# Rate Limit Middleware (Enhanced)
# =============================================================================


class EnhancedRateLimitMiddleware(BaseHTTPMiddleware):
    """Enhanced rate limiting with per-endpoint and per-IP tracking."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from utils import check_rate_limit

        from .common import _client_ip_for_request, _is_rate_limited_path, _rate_limit_error_payload

        client_ip = _client_ip_for_request(request)

        # Security enhancement: Only allow bypass for specific admin endpoints in development
        if (client_ip in {"127.0.0.1", "::1", "::ffff:127.0.0.1"} 
            and os.environ.get("ENV") != "production"
            and not request.url.path.startswith("/admin/")):
            return await call_next(request)

        # Check if this path should be rate limited
        if _is_rate_limited_path(request.url.path):
            if not check_rate_limit(client_ip, request.url.path):
                return Response(
                    status_code=429,
                    content=_rate_limit_error_payload(),
                    headers={"Retry-After": "60"},
                )

        return await call_next(request)


# =============================================================================
# Input Sanitization Helpers
# =============================================================================


def sanitize_html(text: str) -> str:
    """Safely remove HTML tags and escape special characters using bleach."""
    import bleach

    if not text:
        return ""
    # Clean HTML using bleach with a very restrictive whitelist (none)
    # to match the current intent of removing all tags.
    clean = bleach.clean(text, tags=[], attributes={}, strip=True)
    return clean


def safe_contains(haystack: str, needle: str) -> bool:
    """Safely check if haystack contains needle (case-insensitive)."""
    if not haystack or not needle:
        return False
    return needle.lower() in haystack.lower()


# =============================================================================
# Middleware Factory
# =============================================================================


def create_security_middleware(app):
    """Create and add all security middleware to the app."""
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeMiddleware)
    app.add_middleware(EnhancedRateLimitMiddleware)
    log.info("Security middleware configured")
    return app


# =============================================================================
# Dependency Injectors for Route Protection
# =============================================================================


from core.auth import verify_admin_jwt

async def admin_auth(request: Request) -> str:
    """Dependency for JWT-based admin authentication."""
    from .common import _static_admin_token_authorized

    if _static_admin_token_authorized(request):
        return "emergency-admin"

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = auth_header.split("Bearer ")[1]
    if not verify_admin_jwt(token):
        raise HTTPException(status_code=403, detail="Not authorized")
    return "admin"



async def valid_cluster_id(cluster_id: str) -> str:
    """Dependency for cluster_id validation."""
    return validate_cluster_id(cluster_id)


async def valid_date(date: str) -> str:
    """Dependency for date validation."""
    return validate_date(date)
