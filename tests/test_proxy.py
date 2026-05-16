"""
Test the proxy endpoint to ensure it handles valid and invalid URLs correctly.
"""
from fastapi.testclient import TestClient
from core.api_fast import app

client = TestClient(app)


def test_proxy_valid_url():
    """Test that the proxy endpoint returns a 200 status for valid URLs."""
    response = client.get(
        "/proxy?url=https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"


def test_proxy_invalid_url():
    """Test that the proxy endpoint returns a 400 status for invalid URLs."""
    response = client.get("/proxy?url=invalid-url")
    assert response.status_code == 400


def test_proxy_missing_url():
    """Test that the proxy endpoint returns a 400 status when URL is missing."""
    response = client.get("/proxy")
    assert response.status_code == 400


def test_proxy_localhost_url():
    """Test that the proxy endpoint blocks localhost URLs."""
    response = client.get("/proxy?url=http://localhost/test.jpg")
    assert response.status_code == 400


def test_proxy_rate_limiting():
    """Test that the proxy endpoint enforces rate limiting."""
    # Make multiple requests to trigger rate limiting
    for _ in range(101):
        response = client.get(
            "/proxy?url=https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png"
        )
    # The 101st request should be rate-limited
    assert response.status_code == 429
