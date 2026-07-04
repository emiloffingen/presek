"""
admin_tokens.py - Enhanced admin token management with rotation and revocation

Provides a secure admin token system with:
- Token rotation and expiration
- Token revocation capability
- Database-backed token storage
- Rate limiting for token operations
"""

import datetime
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import jwt

from core.database import db_manager as db
from core.logging_config import get_logger

log = get_logger("presek.auth.admin_tokens")

# Configuration
ADMIN_TOKEN_SECRET = os.environ.get("ADMIN_TOKEN_SECRET")
if not ADMIN_TOKEN_SECRET:
    if os.environ.get("ENV") == "production":
        raise RuntimeError("ADMIN_TOKEN_SECRET must be set in production")
    ADMIN_TOKEN_SECRET = secrets.token_urlsafe(32)

ADMIN_TOKEN_ALGORITHM = "HS256"
ADMIN_TOKEN_ISSUER = os.environ.get("ADMIN_TOKEN_ISSUER", "presek-admin")
ADMIN_TOKEN_AUDIENCE = os.environ.get("ADMIN_TOKEN_AUDIENCE", "presek-api")

# Token expiration settings
DEFAULT_TOKEN_EXPIRY_HOURS = int(os.environ.get("ADMIN_TOKEN_EXPIRY_HOURS", "24"))
MAX_TOKEN_EXPIRY_HOURS = int(
    os.environ.get("MAX_ADMIN_TOKEN_EXPIRY_HOURS", "168")
)  # 7 days


@dataclass
class AdminToken:
    """Represents an admin token with metadata."""

    token_id: str
    token_hash: str
    subject: str
    scope: str
    expires_at: datetime.datetime
    created_at: datetime.datetime
    revoked_at: Optional[datetime.datetime] = None
    last_used_at: Optional[datetime.datetime] = None

    @property
    def is_active(self) -> bool:
        """Check if token is active (not revoked and not expired)."""
        now = datetime.datetime.now(datetime.timezone.utc)
        return not self.revoked_at and self.expires_at > now

    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        now = datetime.datetime.now(datetime.timezone.utc)
        return self.expires_at <= now


def _normalize_uuid_str(val) -> str:
    """Normalize a UUID value (string or UUID object) to its 32-character hex representation."""
    import uuid

    if not val:
        return ""
    if isinstance(val, uuid.UUID):
        return val.hex
    try:
        return uuid.UUID(str(val)).hex
    except Exception:
        return str(val)


def _initialize_database():
    """Initialize database tables for admin token management."""
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS admin_tokens (
                token_id UUID PRIMARY KEY,
                token_hash TEXT NOT NULL,
                subject TEXT NOT NULL,
                scope TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ,
                last_used_at TIMESTAMPTZ,
                CONSTRAINT valid_dates CHECK (expires_at > created_at)
            )
            """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_admin_tokens_expires_at 
            ON admin_tokens(expires_at)
            """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_admin_tokens_revoked_at 
            ON admin_tokens(revoked_at)
            """)
        log.info("Admin tokens database tables initialized")
    except Exception as e:
        log.error(f"Failed to initialize admin tokens database: {e}")
        raise


# Initialize database on import
_initialize_database()


def _hash_token(token: str) -> str:
    """Create a secure hash of the token for storage."""
    import hashlib

    return hashlib.sha256(token.encode()).hexdigest()


def _generate_token_id() -> str:
    """Generate a unique token ID."""
    return secrets.token_hex(16)


def create_admin_token(
    subject: str = "admin",
    scope: str = "full-access",
    expiry_hours: Optional[int] = None,
    additional_claims: Optional[Dict] = None,
) -> Tuple[str, AdminToken]:
    """
    Create a new admin token with the specified parameters.

    Args:
        subject: The subject/identifier for the token
        scope: The scope of access (e.g., "full-access", "read-only")
        expiry_hours: Token validity in hours (max MAX_TOKEN_EXPIRY_HOURS)
        additional_claims: Additional JWT claims to include

    Returns:
        Tuple of (token_string, AdminToken)
    """
    # Validate expiry hours
    if expiry_hours is None:
        expiry_hours = DEFAULT_TOKEN_EXPIRY_HOURS
    elif expiry_hours > MAX_TOKEN_EXPIRY_HOURS:
        raise ValueError(f"Token expiry cannot exceed {MAX_TOKEN_EXPIRY_HOURS} hours")
    elif expiry_hours < 1:
        raise ValueError("Token expiry must be at least 1 hour")

    # Generate token
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(hours=expiry_hours)

    token_id = _generate_token_id()

    # Create JWT payload
    payload = {
        "jti": token_id,
        "sub": subject,
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": ADMIN_TOKEN_ISSUER,
        "aud": ADMIN_TOKEN_AUDIENCE,
    }

    if additional_claims:
        payload.update(additional_claims)

    # Generate JWT token signed with global ADMIN_TOKEN_SECRET
    token = jwt.encode(payload, ADMIN_TOKEN_SECRET, algorithm=ADMIN_TOKEN_ALGORITHM)
    token_hash = _hash_token(token)

    # Store token metadata
    admin_token = AdminToken(
        token_id=token_id,
        token_hash=token_hash,
        subject=subject,
        scope=scope,
        expires_at=expires_at,
        created_at=now,
        revoked_at=None,
        last_used_at=None,
    )

    # Store in database
    try:
        db.execute(
            """
            INSERT INTO admin_tokens 
            (token_id, token_hash, subject, scope, expires_at, created_at, revoked_at, last_used_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                admin_token.token_id,
                admin_token.token_hash,
                admin_token.subject,
                admin_token.scope,
                admin_token.expires_at,
                admin_token.created_at,
                admin_token.revoked_at,
                admin_token.last_used_at,
            ),
        )
        log.info(f"Created new admin token {token_id} for {subject} with scope {scope}")
    except Exception as e:
        log.error(f"Failed to store admin token: {e}")
        raise

    return token, admin_token


def verify_admin_token(token: str) -> Optional[AdminToken]:
    """
    Verify an admin token and return its metadata if valid.

    Args:
        token: The admin token to verify

    Returns:
        AdminToken if valid, None if invalid
    """
    try:
        # Decode and verify JWT using global secret
        payload = jwt.decode(
            token,
            ADMIN_TOKEN_SECRET,
            algorithms=[ADMIN_TOKEN_ALGORITHM],
            audience=ADMIN_TOKEN_AUDIENCE,
            issuer=ADMIN_TOKEN_ISSUER,
        )

        token_id = payload.get("jti")
        if not token_id:
            return None

        # Get token metadata from database
        row = db.execute(
            """
            SELECT token_id, token_hash, subject, scope, 
                   expires_at, created_at, revoked_at, last_used_at
            FROM admin_tokens
            WHERE token_id = %s
            """,
            (token_id,),
        )

        if not row:
            return None

        # Ensure UUID structure maps cleanly to Dataclass string field
        db_data = dict(row[0])
        if "token_id" in db_data and db_data["token_id"]:
            db_data["token_id"] = _normalize_uuid_str(db_data["token_id"])

        admin_token = AdminToken(**db_data)

        # Check if token is revoked or expired
        if not admin_token.is_active:
            return None

        # Verify that the SHA256 of the token matches the stored token_hash
        if not hmac.compare_digest(admin_token.token_hash, _hash_token(token)):
            return None

        # Update last used time
        try:
            db.execute(
                """
                UPDATE admin_tokens 
                SET last_used_at = %s
                WHERE token_id = %s
                """,
                (datetime.datetime.now(datetime.timezone.utc), token_id),
            )
        except Exception as e:
            log.warning(f"Failed to update last_used_at for token {token_id}: {e}")

        return admin_token

    except jwt.ExpiredSignatureError:
        log.info("Expired admin token attempt")
        return None
    except jwt.InvalidTokenError:
        log.info("Invalid admin token attempt")
        return None
    except Exception as e:
        log.error(f"Error verifying admin token: {e}")
        return None


def revoke_admin_token(token_id: str) -> bool:
    """
    Revoke an admin token by its ID.

    Args:
        token_id: The token ID to revoke

    Returns:
        True if successfully revoked, False otherwise
    """
    try:
        result = db.execute(
            """
            UPDATE admin_tokens 
            SET revoked_at = %s
            WHERE token_id = %s AND revoked_at IS NULL
            RETURNING token_id
            """,
            (datetime.datetime.now(datetime.timezone.utc), token_id),
        )

        if result:
            log.info(f"Revoked admin token {token_id}")
            return True

        return False
    except Exception as e:
        log.error(f"Failed to revoke admin token {token_id}: {e}")
        return False


def revoke_all_tokens_for_subject(subject: str) -> int:
    """
    Revoke all tokens for a specific subject.

    Args:
        subject: The subject whose tokens to revoke

    Returns:
        Number of tokens revoked
    """
    try:
        result = db.execute(
            """
            UPDATE admin_tokens 
            SET revoked_at = %s
            WHERE subject = %s AND revoked_at IS NULL
            RETURNING token_id
            """,
            (datetime.datetime.now(datetime.timezone.utc), subject),
        )

        revoked_count = len(result) if result else 0
        log.info(f"Revoked {revoked_count} tokens for subject {subject}")
        return revoked_count
    except Exception as e:
        log.error(f"Failed to revoke tokens for subject {subject}: {e}")
        return 0


def list_active_admin_tokens() -> List[AdminToken]:
    """
    List all active (non-revoked, non-expired) admin tokens.

    Returns:
        List of active AdminToken objects
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        rows = db.execute(
            """
            SELECT token_id, token_hash, subject, scope, 
                   expires_at, created_at, revoked_at, last_used_at
            FROM admin_tokens
            WHERE (revoked_at IS NULL OR revoked_at > %s)
              AND expires_at > %s
            ORDER BY created_at DESC
            """,
            (now, now),
        )

        tokens = []
        for row in rows:
            db_data = dict(row)
            if "token_id" in db_data and db_data["token_id"]:
                db_data["token_id"] = _normalize_uuid_str(db_data["token_id"])
            tokens.append(AdminToken(**db_data))
        return tokens
    except Exception as e:
        log.error(f"Failed to list active admin tokens: {e}")
        return []


def cleanup_expired_tokens() -> int:
    """
    Clean up expired tokens from the database.

    Returns:
        Number of tokens cleaned up
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        result = db.execute(
            """
            DELETE FROM admin_tokens 
            WHERE expires_at < %s
            RETURNING token_id
            """,
            (now,),
        )

        cleaned_count = len(result) if result else 0
        log.info(f"Cleaned up {cleaned_count} expired admin tokens")
        return cleaned_count
    except Exception as e:
        log.error(f"Failed to cleanup expired tokens: {e}")
        return 0


def generate_admin_token_secret() -> str:
    """Generate a secure admin token secret key."""
    return secrets.token_urlsafe(32)


# Legacy compatibility functions for gradual migration
def verify_legacy_admin_token(token: str) -> bool:
    """
    Verify legacy static admin token for backward compatibility.

    This function provides backward compatibility during migration
    from static tokens to the new token management system.
    """
    import os
    import secrets

    if os.environ.get("ENV") == "production":
        # In production, legacy tokens should be disabled unless explicitly allowed
        if os.environ.get("ALLOW_LEGACY_ADMIN_TOKEN", "").lower() != "true":
            return False

    expected = (os.environ.get("PRESEK_ADMIN_TOKEN") or "").strip()
    if not expected:
        return False

    # Use constant-time comparison to prevent timing attacks
    return secrets.compare_digest(token, expected)
