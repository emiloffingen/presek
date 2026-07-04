"""
Test security headers and middleware functionality.
"""
import pytest

from core.auth import create_jwt_token, decode_jwt
from routes.security import SecurityHeadersMiddleware, generate_csrf_token, validate_csrf_token


def test_csrf_token_generation_and_validation():
    """Test CSRF token generation and validation."""
    token = generate_csrf_token()
    assert token is not None
    assert ":" in token
    
    # Valid token should validate
    assert validate_csrf_token(token) is True
    
    # Invalid tokens should fail
    assert validate_csrf_token("invalid") is False
    assert validate_csrf_token("") is False
    assert validate_csrf_token("no_colon_here") is False


def test_jwt_token_creation_and_decoding():
    """Test JWT token creation and decoding."""
    token = create_jwt_token("test_user", {"role": "user"})
    assert token is not None
    assert isinstance(token, str)

    payload = decode_jwt(token)
    assert payload is not None
    assert payload["sub"] == "test_user"
    assert payload["role"] == "user"
    assert "iat" in payload
    assert "exp" in payload
    assert "jti" in payload


@pytest.mark.asyncio
async def test_security_headers_middleware():
    """Test that security headers middleware adds expected headers."""
    from starlette.datastructures import Headers
    from starlette.responses import JSONResponse

    middleware = SecurityHeadersMiddleware(lambda scope, receive, send: None)
    request = type(
        "Request",
        (),
        {
            "headers": Headers({}),
        },
    )()

    async def call_next(_request):
        return JSONResponse({"message": "test"})

    response = await middleware.dispatch(request, call_next)
    
    # Check critical security headers
    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"
    
    assert "Strict-Transport-Security" in response.headers
    
    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src" in csp
    assert "style-src" in csp
    
    assert "Referrer-Policy" in response.headers
    assert "Permissions-Policy" in response.headers


def test_input_validation_functions():
    """Test input validation helper functions."""
    from routes.security import (
        validate_cluster_id,
        validate_date,
        validate_email,
        validate_list_param,
        validate_string_param,
    )
    
    # Test cluster ID validation
    valid_cluster_id = validate_cluster_id("abc123")
    assert valid_cluster_id == "abc123"
    
    with pytest.raises(Exception):  # Should raise for invalid format
        validate_cluster_id("!")
    
    # Test date validation
    valid_date = validate_date("2023-01-01")
    assert valid_date == "2023-01-01"
    
    with pytest.raises(Exception):  # Should raise for invalid date
        validate_date("not-a-date")
    
    # Test email validation
    valid_email = validate_email("test@example.com")
    assert valid_email == "test@example.com"
    
    with pytest.raises(Exception):  # Should raise for invalid email
        validate_email("not-an-email")
    
    # Test string parameter validation
    valid_string = validate_string_param("test", "param", max_length=10)
    assert valid_string == "test"
    
    with pytest.raises(Exception):  # Should raise for too long string
        validate_string_param("a" * 100, "param", max_length=10)
    
    # Test list parameter validation
    valid_list = validate_list_param(["item1", "item2"], "param")
    assert valid_list == ["item1", "item2"]
    
    with pytest.raises(Exception):  # Should raise for non-list
        validate_list_param("not a list", "param")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
