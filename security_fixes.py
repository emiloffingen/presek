# Security Fixes for Presek (Consolidated into routes/security.py)

from routes.security import (
    generate_csrf_token,
    validate_csrf_token,
    verify_csrf_token,
    SecurityHeadersMiddleware as EnhancedSecurityHeadersMiddleware,
    EnhancedRateLimitMiddleware,
    CSRF_TOKEN_EXPIRY,
)

def apply_security_fixes(app):
    """Apply all security fixes to the FastAPI app (now done automatically inside routes/security.py)."""
    # Middleware is already configured via create_security_middleware in routes.security
    # This function is kept for backward compatibility with manual deployment checks/docs.
    print("Security fixes are now fully integrated and applied automatically inside routes.security!")