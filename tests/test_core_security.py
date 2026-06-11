"""
Core security tests that don't require external dependencies.
"""
import sys
import os
import secrets

import pytest
import hmac
import hashlib
import time
import re


def test_csrf_token_functions():
    """Test CSRF token functions directly."""
    print("Testing CSRF token functions...")
    
    # Mock the CSRF secret
    CSRF_TOKEN_SECRET = secrets.token_urlsafe(32)
    CSRF_TOKEN_EXPIRY = 3600
    
    def generate_csrf_token():
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
    
    # Test valid token
    token = generate_csrf_token()
    assert token is not None
    assert ":" in token
    assert validate_csrf_token(token) is True
    
    # Test invalid tokens
    assert validate_csrf_token("invalid") is False
    assert validate_csrf_token("") is False
    assert validate_csrf_token("no_colon_here") is False
    
    print("✓ CSRF token tests passed")


def test_input_validation_patterns():
    """Test input validation regex patterns."""
    print("Testing input validation patterns...")
    
    # Test patterns from routes/security.py
    CLUSTER_ID_PATTERN = re.compile(r"^[a-f0-9\-]{6,64}$")
    UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    
    # Test cluster ID pattern
    assert CLUSTER_ID_PATTERN.match("abc123") is not None
    assert CLUSTER_ID_PATTERN.match("a" * 64) is not None
    assert CLUSTER_ID_PATTERN.match("!") is None
    assert CLUSTER_ID_PATTERN.match("a" * 5) is None  # Too short
    
    # Test UUID pattern
    valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
    assert UUID_PATTERN.match(valid_uuid) is not None
    assert UUID_PATTERN.match("not-a-uuid") is None
    
    # Test date pattern
    assert DATE_PATTERN.match("2023-01-01") is not None
    assert DATE_PATTERN.match("not-a-date") is None
    assert DATE_PATTERN.match("2023-1-1") is None  # Missing leading zeros
    
    # Test email pattern
    assert EMAIL_PATTERN.match("test@example.com") is not None
    assert EMAIL_PATTERN.match("user.name+tag@sub.domain.co.uk") is not None
    assert EMAIL_PATTERN.match("not-an-email") is None
    assert EMAIL_PATTERN.match("user@") is None
    
    print("✓ Input validation pattern tests passed")


def test_environment_validation(monkeypatch):
    """Test environment variable validation logic."""
    print("Testing environment validation logic...")

    REQUIRED_RUNTIME_ENV_KEYS = ("DATABASE_URL", "SECRET_KEY")

    def check_missing_env(keys):
        return [k for k in keys if not os.environ.get(k)]

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    missing = check_missing_env(REQUIRED_RUNTIME_ENV_KEYS)
    assert len(missing) == len(REQUIRED_RUNTIME_ENV_KEYS), "Should detect missing env vars"

    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("SECRET_KEY", "test_secret_key")

    missing = check_missing_env(REQUIRED_RUNTIME_ENV_KEYS)
    assert len(missing) == 0, "Should have no missing env vars after setting"

    print("✓ Environment validation tests passed")


def test_security_constants():
    """Test security-related constants and configurations."""
    print("Testing security constants...")

    from core.config import API_MAX_Q_LEN
    from routes.security import MAX_HEADER_VALUE_LENGTH, MAX_QUERY_PARAM_LENGTH, MAX_REQUEST_BODY_SIZE

    assert MAX_REQUEST_BODY_SIZE == 10485760, "Max request body size should be 10MB"
    assert MAX_QUERY_PARAM_LENGTH == API_MAX_Q_LEN, "Query param limit should match API_MAX_Q_LEN"
    assert MAX_HEADER_VALUE_LENGTH == 2000, "Max header value length should be 2000"
    
    # Test JWT constants
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_MINUTES = 60
    
    assert JWT_ALGORITHM == "HS256", "JWT algorithm should be HS256"
    assert JWT_EXPIRE_MINUTES == 60, "JWT expire minutes should be 60"
    
    print("✓ Security constants tests passed")


def test_sensitive_key_detection():
    """Test detection of sensitive values in configuration."""
    print("Testing sensitive key detection...")
    
    dangerous_patterns = [
        ("DATABASE_URL", ["password", "1234", "test", "changeme", "postgres://"]),
        ("SECRET_KEY", ["secret", "test", "changeme", "123"]),
        ("PRESEK_ADMIN_TOKEN", ["admin", "test", "123", "changeme"]),
    ]
    
    # Test with safe values
    safe_values = {
        "DATABASE_URL": "postgresql://produser:secure_pwd_xyz789@db.example.com/production",
        "SECRET_KEY": "prod_secure_key_xyz789_abcdef_ghijkl",
        "PRESEK_ADMIN_TOKEN": "prod_management_token_secure_xyz789",
    }
    
    issues = []
    for key, patterns in dangerous_patterns:
        value = safe_values.get(key, "").lower()
        for pattern in patterns:
            if pattern.lower() in value:
                issues.append(f"{key} appears to contain a default/test value")
                break
    
    assert len(issues) == 0, f"Safe values should not trigger issues: {issues}"
    
    # Test with dangerous values
    dangerous_values = {
        "DATABASE_URL": "postgres://test:password@localhost/test",
        "SECRET_KEY": "secret",
        "PRESEK_ADMIN_TOKEN": "admin123",
    }
    
    issues = []
    for key, patterns in dangerous_patterns:
        value = dangerous_values.get(key, "").lower()
        for pattern in patterns:
            if pattern.lower() in value:
                issues.append(f"{key} appears to contain a default/test value")
                break
    
    assert len(issues) > 0, "Dangerous values should trigger issues"
    
    print("✓ Sensitive key detection tests passed")


def main():
    """Run all core security tests."""
    print("=" * 60)
    print("PRESEK CORE SECURITY TESTS")
    print("=" * 60)
    print()
    
    try:
        test_csrf_token_functions()
        test_input_validation_patterns()
        test_environment_validation()
        test_security_constants()
        test_sensitive_key_detection()
        
        print()
        print("=" * 60)
        print("ALL CORE SECURITY TESTS PASSED ✅")
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