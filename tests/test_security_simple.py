"""
Simple security tests that don't require external dependencies.
"""

import sys

sys.path.append(".")


def test_csrf_token_generation_and_validation():
    """Test CSRF token generation and validation."""
    from routes.security import generate_csrf_token, validate_csrf_token

    print("Testing CSRF token generation and validation...")

    # Test valid token
    token = generate_csrf_token()
    assert token is not None, "Token generation failed"
    assert ":" in token, "Token should contain colon separator"

    # Valid token should validate
    assert validate_csrf_token(token) is True, "Valid token should pass validation"

    # Invalid tokens should fail
    assert validate_csrf_token("invalid") is False, "Invalid token should fail"
    assert validate_csrf_token("") is False, "Empty token should fail"
    assert validate_csrf_token("no_colon_here") is False, "Token without colon should fail"

    print("✓ CSRF token tests passed")


def test_jwt_token_creation_and_decoding():
    """Test JWT token creation and decoding."""
    from core.auth import create_jwt_token, decode_jwt

    print("Testing JWT token creation and decoding...")

    token = create_jwt_token("test_user", {"role": "user"})
    assert token is not None, "Token creation failed"
    assert isinstance(token, str), "Token should be a string"

    payload = decode_jwt(token)
    assert payload is not None, "Token decoding failed"
    assert payload["sub"] == "test_user", "Subject should match"
    assert payload["role"] == "user", "Role should match"
    assert "iat" in payload, "Issued at time should be present"
    assert "exp" in payload, "Expiration time should be present"
    assert "jti" in payload, "JWT ID should be present"

    print("✓ JWT token tests passed")


def test_input_validation_functions():
    """Test input validation helper functions."""
    from routes.security import (
        validate_cluster_id,
        validate_date,
        validate_email,
        validate_list_param,
        validate_string_param,
    )

    print("Testing input validation functions...")

    valid_cluster_id = validate_cluster_id("abc123")
    assert valid_cluster_id == "abc123", "Valid cluster ID should pass"

    valid_date = validate_date("2023-01-01")
    assert valid_date == "2023-01-01", "Valid date should pass"

    valid_email = validate_email("test@example.com")
    assert valid_email == "test@example.com", "Valid email should pass"

    valid_string = validate_string_param("test", "param", max_length=10)
    assert valid_string == "test", "Valid string should pass"

    valid_list = validate_list_param(["item1", "item2"], "param")
    assert valid_list == ["item1", "item2"], "Valid list should pass"


async def test_security_headers_middleware():
    """Test that security headers middleware adds expected headers."""
    from starlette.datastructures import Headers
    from starlette.responses import JSONResponse

    from routes.security import SecurityHeadersMiddleware

    print("Testing security headers middleware...")

    middleware = SecurityHeadersMiddleware(lambda scope, receive, send: None)
    request = type(
        "Request",
        (),
        {
            "headers": Headers({}),
            "cookies": {},
        },
    )()

    async def call_next(_request):
        return JSONResponse({"message": "test"})

    response = await middleware.dispatch(request, call_next)

    # Check critical security headers
    assert "X-Content-Type-Options" in response.headers, "X-Content-Type-Options header missing"
    assert response.headers["X-Content-Type-Options"] == "nosniff", "X-Content-Type-Options should be nosniff"

    assert "X-Frame-Options" in response.headers, "X-Frame-Options header missing"
    assert response.headers["X-Frame-Options"] == "DENY", "X-Frame-Options should be DENY"

    assert "Strict-Transport-Security" in response.headers, "Strict-Transport-Security header missing"

    assert "Content-Security-Policy" in response.headers, "Content-Security-Policy header missing"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp, "CSP should include default-src 'self'"
    assert "script-src" in csp, "CSP should include script-src"
    assert "style-src" in csp, "CSP should include style-src"

    assert "Referrer-Policy" in response.headers, "Referrer-Policy header missing"
    assert "Permissions-Policy" in response.headers, "Permissions-Policy header missing"

    print("✓ Security headers middleware tests passed")


def main():
    """Run all security tests."""
    print("=" * 60)
    print("PRESEK SECURITY TESTS")
    print("=" * 60)
    print()

    try:
        test_csrf_token_generation_and_validation()
        test_jwt_token_creation_and_decoding()
        test_input_validation_functions()
        import asyncio

        asyncio.run(test_security_headers_middleware())

        print()
        print("=" * 60)
        print("ALL SECURITY TESTS PASSED ✅")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
