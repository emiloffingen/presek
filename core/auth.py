"""
auth.py - JWT-based authentication utilities for Presek API

Provides JWT token generation, validation, and middleware for enhanced
security over the previous admin token system.
"""

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException

# Configuration
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    if os.environ.get("ENV") == "production":
        raise RuntimeError("JWT_SECRET must be set in production")
    JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
JWT_ISSUER = os.environ.get("JWT_ISSUER", "presek-api")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "presek-admin")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))


def create_jwt_token(subject: str, additional_claims: dict[str, Any] | None = None) -> str:
    """Create a new JWT token."""
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
        "jti": secrets.token_hex(16),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_admin_jwt() -> str:
    """Create a JWT token for admin access."""
    return create_jwt_token("admin", {"role": "admin", "scope": "full-access"})


def verify_admin_jwt(token: str) -> bool:
    """Verify admin JWT token."""
    try:
        payload = decode_jwt(token)
        return payload.get("role") == "admin" and payload.get("scope") == "full-access"
    except Exception:
        return False
