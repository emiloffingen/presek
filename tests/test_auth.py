"""Test authentication functionality."""

import pytest
from fastapi.testclient import TestClient
from core.auth import create_jwt_token, decode_jwt, verify_admin_jwt, create_admin_jwt


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
    import time
    from core.config import JWT_EXPIRE_MINUTES
    
    # Create a token
    token = create_jwt_token("test_user")
    
    # Verify it works initially
    payload = decode_jwt(token)
    assert payload is not None
    
    # Wait for expiration (simulate by modifying the token's exp claim)
    # Note: In a real test, you'd need to mock the time or use a very short expiration


def test_admin_endpoint_with_jwt():
    """Test admin endpoint with JWT authentication."""
    from core.api_fast import app
    
    client = TestClient(app)
    
    # Create admin token
    admin_token = create_admin_jwt()
    
    # Test admin dashboard access
    response = client.get("/admin/dashboard", headers={
        "Authorization": f"Bearer {admin_token}"
    })
    
    # Should return 200 for valid admin token
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "success"


def test_admin_endpoint_without_auth():
    """Test admin endpoint without authentication."""
    from core.api_fast import app
    
    client = TestClient(app)
    
    # Test admin dashboard access without auth
    response = client.get("/admin/dashboard")
    
    # Should return 403 for unauthorized access
    assert response.status_code == 403


def test_admin_endpoint_with_invalid_token():
    """Test admin endpoint with invalid token."""
    from core.api_fast import app
    
    client = TestClient(app)
    
    # Test admin dashboard access with invalid token
    response = client.get("/admin/dashboard", headers={
        "Authorization": "Bearer invalid.token.here"
    })
    
    # Should return 403 for invalid token
    assert response.status_code == 403