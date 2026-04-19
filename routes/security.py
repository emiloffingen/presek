"""
security.py - Centralized security utilities and middleware for Presek API
"""
import os
import re
import secrets
import logging
from typing import Callable, Awaitable
from fastapi import Request, HTTPException
from starlette.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("presek")

# =============================================================================
# Input Validation Helpers
# =============================================================================

CLUSTER_ID_PATTERN = re.compile(r'^[a-f0-9]{6,64}$')
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


def validate_cluster_id(cluster_id: str, param_name: str = "cluster_id") -> str:
    """Validate cluster ID format (hex string, 6-64 chars)."""
    if not cluster_id:
        raise HTTPException(status_code=400, detail=f"{param_name} is required")
    if not isinstance(cluster_id, str):
        raise HTTPException(status_code=400, detail=f"{param_name} must be a string")
    if not CLUSTER_ID_PATTERN.match(cluster_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}. Must be 6-64 character hexadecimal string."
        )
    return cluster_id


def validate_date(date_str: str, param_name: str = "date") -> str:
    """Validate date format (YYYY-MM-DD)."""
    if not date_str:
        raise HTTPException(status_code=400, detail=f"{param_name} is required")
    if not DATE_PATTERN.match(date_str):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {param_name}. Must be in YYYY-MM-DD format."
        )
    return date_str


def validate_email(email: str, param_name: str = "email") -> str:
    """Validate email format."""
    if not email:
        raise HTTPException(status_code=400, detail=f"{param_name} is required")
    email = email.strip().lower()
    if len(email) > 254:
        raise HTTPException(status_code=400, detail=f"{param_name} too long")
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail=f"Invalid {param_name}")
    return email


def validate_string_param(value: str, param_name: str, max_length: int = 200, min_length: int = 0, allow_empty: bool = True) -> str:
    """Validate a string parameter with length constraints."""
    if value is None:
        if allow_empty:
            return ""
        raise HTTPException(status_code=400, detail=f"{param_name} is required")
    
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{param_name} must be a string")
    
    value = value.strip()
    if not allow_empty and not value:
        raise HTTPException(status_code=400, detail=f"{param_name} is required")
    
    if len(value) > max_length:
        raise HTTPException(status_code=400, detail=f"{param_name} exceeds maximum length of {max_length}")
    
    if len(value) < min_length and value:
        raise HTTPException(status_code=400, detail=f"{param_name} must be at least {min_length} characters")
    
    return value


def validate_list_param(items, param_name: str, max_items: int = 20, max_item_length: int = 100) -> list:
    """Validate a list parameter."""
    if items is None:
        return []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail=f"{param_name} must be a list")
    if len(items) > max_items:
        raise HTTPException(status_code=400, detail=f"{param_name} exceeds maximum of {max_items} items")
    result = []
    for item in items:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail=f"All items in {param_name} must be strings")
        cleaned = item.strip()
        if len(cleaned) > max_item_length:
            raise HTTPException(status_code=400, detail=f"Items in {param_name} exceed maximum length of {max_item_length}")
        if cleaned:
            result.append(cleaned)
    return result


# =============================================================================
# Authentication Helpers
# =============================================================================

def get_admin_token() -> str:
    """Get the configured admin token."""
    return (os.environ.get("PRESEK_ADMIN_TOKEN") or "").strip()


def verify_admin_token(request: Request) -> bool:
    """Verify the X-Admin-Token header matches the configured token."""
    token = (request.headers.get("X-Admin-Token") or "").strip()
    expected = get_admin_token()
    if not expected:
        return False
    if not token:
        return False
    return secrets.compare_digest(token, expected)


def require_admin_token(request: Request) -> None:
    """Raise 403 if not authenticated as admin."""
    if not verify_admin_token(request):
        raise HTTPException(status_code=403, detail="Forbidden")


def verify_sync_token(request: Request) -> str:
    """Extract and validate sync token from request."""
    from .common import _extract_sync_token
    token = _extract_sync_token(request)
    if not token or len(token) < 12:
        raise HTTPException(status_code=400, detail="Missing or invalid sync token")
    return token


# =============================================================================
# Security Headers Middleware
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp
        
        # Permissions Policy
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )
        
        # Cross-Origin policies
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        
        return response


# =============================================================================
# Request Size Limiting Middleware
# =============================================================================

MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_QUERY_PARAM_LENGTH = 1000
MAX_HEADER_VALUE_LENGTH = 2000


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request sizes."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check declared body size before reading the request downstream.
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BODY_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="Request body exceeds maximum size"
                    )
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Content-Length header")

        # Check query parameters
        for key, value in request.query_params.items():
            if len(value) > MAX_QUERY_PARAM_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Query parameter '{key}' exceeds maximum length"
                )
        
        # Check headers
        for key, value in request.headers.items():
            if isinstance(value, str) and len(value) > MAX_HEADER_VALUE_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"Header '{key}' exceeds maximum length"
                )
        
        response = await call_next(request)
        return response


# =============================================================================
# Rate Limit Middleware (Enhanced)
# =============================================================================

class EnhancedRateLimitMiddleware(BaseHTTPMiddleware):
    """Enhanced rate limiting with per-endpoint and per-IP tracking."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from .common import _client_ip_for_request, _is_rate_limited_path
        from utils import check_rate_limit
        from .common import _rate_limit_error_payload
        
        client_ip = _client_ip_for_request(request)
        
        # Skip rate limiting for localhost and private IPs in development
        if client_ip in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}:
            return await call_next(request)
        
        # Check if this path should be rate limited
        if _is_rate_limited_path(request.url.path):
            if not check_rate_limit(client_ip, request.url.path):
                return Response(
                    status_code=429,
                    content=_rate_limit_error_payload(),
                    headers={"Retry-After": "60"}
                )
        
        return await call_next(request)


# =============================================================================
# Input Sanitization Helpers
# =============================================================================

def sanitize_html(text: str) -> str:
    """Remove HTML tags and escape special characters."""
    import html
    if not text:
        return ""
    text = re.sub(r'<[^>]*>', '', text)  # Remove HTML tags
    text = html.escape(text)  # Escape HTML entities
    return text


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
    log.info("Security middleware configured")
    return app


# =============================================================================
# Dependency Injectors for Route Protection
# =============================================================================

from fastapi import Depends


async def admin_user(request: Request) -> bool:
    """Dependency for admin-only endpoints."""
    return verify_admin_token(request)


async def valid_cluster_id(cluster_id: str) -> str:
    """Dependency for cluster_id validation."""
    return validate_cluster_id(cluster_id)


async def valid_date(date: str) -> str:
    """Dependency for date validation."""
    return validate_date(date)
