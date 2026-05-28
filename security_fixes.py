# Security Fixes for Presek
# This file contains the security enhancements that should be applied

import os
import secrets
import hmac
import hashlib
import time
from typing import Callable

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# =============================================================================
# CSRF Protection
# =============================================================================

# Initialize CSRF secret - use environment variable or generate a stable one
_CSRF_SECRET_FILE = "/tmp/presek_csrf_secret.txt"
if os.environ.get("CSRF_TOKEN_SECRET"):
    CSRF_TOKEN_SECRET = os.environ.get("CSRF_TOKEN_SECRET")
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


# =============================================================================
# Enhanced Security Headers Middleware
# =============================================================================

class EnhancedSecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add enhanced security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add CSRF token cookie for frontend use
        csrf_token = generate_csrf_token()
        is_production = os.environ.get("ENV") == "production"
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            httponly=False,  # Must be accessible to JavaScript
            secure=is_production,
            samesite="lax",
            max_age=CSRF_TOKEN_EXPIRY,
        )
        
        return response


# =============================================================================
# Enhanced Rate Limit Middleware
# =============================================================================

class EnhancedRateLimitMiddleware(BaseHTTPMiddleware):
    """Enhanced rate limiting with improved security."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        from utils import check_rate_limit
        from routes.common import _client_ip_for_request, _is_rate_limited_path, _rate_limit_error_payload

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


def apply_security_fixes(app):
    """Apply all security fixes to the FastAPI app."""
    # Add enhanced security headers middleware
    app.add_middleware(EnhancedSecurityHeadersMiddleware)
    
    # Replace rate limiting middleware with enhanced version
    # Note: You may need to remove the old middleware first
    app.add_middleware(EnhancedRateLimitMiddleware)
    
    print("Security fixes applied successfully!")