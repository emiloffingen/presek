import os
import datetime
import secrets
import jwt
import pytest
from core.database import db_manager as db

# Set test environment settings
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ADMIN_TOKEN_SECRET", "test-admin-secret-for-jwt-testing-1234567890")


@pytest.fixture(autouse=True)
def setup_test_db():
    """Make sure token database exists for test runtime."""
    from core.admin_tokens import _initialize_database
    _initialize_database()
    yield
    # Clean up test tokens after runs
    try:
        db.execute("DELETE FROM admin_tokens")
    except Exception:
        pass


def test_create_and_verify_admin_token():
    """Test standard admin token creation and verification flow."""
    from core.admin_tokens import create_admin_token, verify_admin_token

    token_str, token_meta = create_admin_token(
        subject="test-admin-subject",
        scope="read-only",
        expiry_hours=2
    )

    assert token_str is not None
    assert token_meta.subject == "test-admin-subject"
    assert token_meta.scope == "read-only"
    assert token_meta.expires_at > token_meta.created_at

    # Verify signature and metadata match
    verified = verify_admin_token(token_str)
    assert verified is not None
    assert verified.token_id == token_meta.token_id
    assert verified.subject == "test-admin-subject"
    assert verified.scope == "read-only"


def test_tampered_signature_verification_fails():
    """Test that tampered JWT signatures fail verification."""
    from core.admin_tokens import create_admin_token, verify_admin_token

    token_str, _ = create_admin_token(subject="security-admin")

    # Tamper with signature suffix
    tampered_token = token_str + "x"
    assert verify_admin_token(tampered_token) is None


def test_token_signed_with_wrong_key_fails():
    """Test that a token signed with an unauthorized external key fails verification."""
    from core.admin_tokens import create_admin_token, verify_admin_token

    _, token_meta = create_admin_token(subject="other-admin")
    
    # Generate token payload signed with a different key
    payload = {
        "jti": token_meta.token_id,
        "sub": "other-admin",
        "scope": token_meta.scope,
        "iat": int(token_meta.created_at.timestamp()),
        "exp": int(token_meta.expires_at.timestamp()),
        "iss": "presek-admin",
        "aud": "presek-api",
    }
    
    wrong_key_token = jwt.encode(payload, "completely-wrong-key-secret-12345", algorithm="HS256")
    assert verify_admin_token(wrong_key_token) is None


def test_token_revocation():
    """Test token revocation flow."""
    from core.admin_tokens import create_admin_token, verify_admin_token, revoke_admin_token

    token_str, token_meta = create_admin_token(subject="revocation-target")
    assert verify_admin_token(token_str) is not None

    # Revoke
    success = revoke_admin_token(token_meta.token_id)
    assert success is True

    # Verification should now fail
    assert verify_admin_token(token_str) is None


def test_revoke_all_tokens_for_subject():
    """Test revoking all active tokens for a specific subject."""
    from core.admin_tokens import create_admin_token, verify_admin_token, revoke_all_tokens_for_subject

    token_str_1, _ = create_admin_token(subject="multi-admin")
    token_str_2, _ = create_admin_token(subject="multi-admin")
    token_str_3, _ = create_admin_token(subject="other-admin")

    assert verify_admin_token(token_str_1) is not None
    assert verify_admin_token(token_str_2) is not None
    assert verify_admin_token(token_str_3) is not None

    # Revoke all for multi-admin
    count = revoke_all_tokens_for_subject("multi-admin")
    assert count == 2

    assert verify_admin_token(token_str_1) is None
    assert verify_admin_token(token_str_2) is None
    assert verify_admin_token(token_str_3) is not None  # Should remain active


def test_list_active_admin_tokens():
    """Test listing active admin tokens excludes expired/revoked ones."""
    from core.admin_tokens import create_admin_token, list_active_admin_tokens, revoke_admin_token

    _, token_meta_1 = create_admin_token(subject="list-admin-1")
    _, token_meta_2 = create_admin_token(subject="list-admin-2")

    active_tokens = list_active_admin_tokens()
    active_ids = {t.token_id for t in active_tokens}
    assert token_meta_1.token_id in active_ids
    assert token_meta_2.token_id in active_ids

    # Revoke one
    revoke_admin_token(token_meta_1.token_id)
    
    active_tokens_after = list_active_admin_tokens()
    active_ids_after = {t.token_id for t in active_tokens_after}
    assert token_meta_1.token_id not in active_ids_after
    assert token_meta_2.token_id in active_ids_after


def test_cleanup_expired_tokens():
    """Test cleaning up expired tokens removes them from the database."""
    from core.admin_tokens import create_admin_token, cleanup_expired_tokens
    
    # We can simulate expired tokens by updating their expires_at in the database
    _, token_meta = create_admin_token(subject="expiring-soon")
    
    past_created_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=10)
    past_expiry_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)
    db.execute(
        "UPDATE admin_tokens SET created_at = %s, expires_at = %s WHERE token_id = %s",
        (past_created_date, past_expiry_date, token_meta.token_id)
    )

    cleaned = cleanup_expired_tokens()
    assert cleaned == 1
