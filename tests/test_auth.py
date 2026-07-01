"""Test authentication functionality."""

import pytest

from core.auth import create_admin_jwt, create_jwt_token, decode_jwt, verify_admin_jwt


def test_jwt_token_creation_and_verification():
    """Test JWT token creation and verification."""
    # Create a token
    token = create_jwt_token("test_user", {"role": "user"})
    assert token is not None
    assert isinstance(token, str)

    # Verify the token
    payload = decode_jwt(token)
    assert payload is not None
    assert payload["sub"] == "test_user"
    assert payload["role"] == "user"
    assert "iat" in payload
    assert "exp" in payload
    assert "jti" in payload
    assert payload["iss"] == "presek-api"
    assert payload["aud"] == "presek-admin"


def test_admin_jwt_creation_and_verification():
    """Test admin JWT token creation and verification."""
    # Create an admin token
    token = create_admin_jwt()
    assert token is not None
    assert isinstance(token, str)

    # Verify it's an admin token
    assert verify_admin_jwt(token) is True

    # Verify the payload
    payload = decode_jwt(token)
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"
    assert payload["scope"] == "full-access"


def test_invalid_jwt_verification():
    """Test verification of invalid JWT tokens."""
    # Test with invalid token
    with pytest.raises(Exception):
        decode_jwt("invalid.token.here")

    # Test with empty token
    with pytest.raises(Exception):
        decode_jwt("")


def test_jwt_expiration():
    """Test JWT token expiration."""

    # Create a token
    token = create_jwt_token("test_user")

    # Verify it works initially
    payload = decode_jwt(token)
    assert payload is not None

    # Wait for expiration (simulate by modifying the token's exp claim)
    # Note: In a real test, you'd need to mock the time or use a very short expiration


def test_verify_admin_accepts_jwt():
    """Test admin verification with JWT authentication."""
    import asyncio

    from routes.admin import verify_admin

    admin_token = create_admin_jwt()
    request = type("Request", (), {"headers": {"Authorization": f"Bearer {admin_token}"}})()

    assert asyncio.run(verify_admin(request)) is True


def test_verify_admin_accepts_static_admin_token(monkeypatch):
    """Test admin verification with the configured static admin token."""
    import asyncio

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("PRESEK_ADMIN_TOKEN", "static-admin-token")
    from routes.admin import verify_admin

    request = type("Request", (), {"headers": {"Authorization": "Bearer static-admin-token"}})()
    assert asyncio.run(verify_admin(request)) is True


def test_static_admin_token_disabled_by_default_in_production(monkeypatch):
    """Production should not accept the static admin token unless explicitly enabled."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ALLOW_STATIC_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("PRESEK_ADMIN_TOKEN", "static-admin-token")
    from routes.common import _static_admin_token_authorized

    request = type("Request", (), {"headers": {"Authorization": "Bearer static-admin-token"}})()
    assert _static_admin_token_authorized(request) is False


def test_admin_endpoint_without_auth():
    """Test admin verification without authentication."""
    import asyncio

    from fastapi import HTTPException

    from routes.admin import verify_admin

    request = type("Request", (), {"headers": {}})()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_admin(request))
    assert exc.value.status_code == 403


def test_admin_endpoint_with_invalid_token():
    """Test admin verification with invalid token."""
    import asyncio

    from fastapi import HTTPException

    from routes.admin import verify_admin

    request = type("Request", (), {"headers": {"Authorization": "Bearer invalid.token.here"}})()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_admin(request))
    assert exc.value.status_code == 403
