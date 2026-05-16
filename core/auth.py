"""
auth.py - JWT-based authentication utilities for Presek API

Provides JWT token generation, validation, and middleware for enhanced
security over the previous admin token system.
"""

import os
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import jwt
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))


class JWTBearer(HTTPBearer):
    """Dependency for JWT token authentication."""
    
    def __init__(self, auto_error: bool = True):
        super(JWTBearer, self).__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super(JWTBearer, self).__call__(request)
        if credentials:
            if not credentials.scheme == "Bearer":
                raise HTTPException(status_code=403, detail="Invalid authentication scheme.")
            if not self.verify_jwt(credentials.credentials):
                raise HTTPException(status_code=403, detail="Invalid token or expired token.")
            return credentials.credentials
        else:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")
    
    def verify_jwt(self, jwt_token: str) -> bool:
        """Verify JWT token validity."""
        try:
            payload = decode_jwt(jwt_token)
            return payload is not None
        except Exception:
            return False


def create_jwt_token(subject: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a new JWT token."""
    payload = {
        "sub": subject,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES),
        "jti": secrets.token_hex(16),
    }
    
    if additional_claims:
        payload.update(additional_claims)
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user(request: Request) -> str:
    """Get the current user from JWT token."""
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        token = token.split("Bearer ")[1]
        payload = decode_jwt(token)
        return payload["sub"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid authentication: {str(e)}")


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


def generate_jwt_secret() -> str:
    """Generate a secure JWT secret key."""
    return secrets.token_urlsafe(32)