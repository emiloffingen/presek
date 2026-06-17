"""HTTP-level security regression tests."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from routes.security import generate_csrf_token

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["SECRET_KEY"] = "test-secret-key-integration"
os.environ["JWT_SECRET"] = "test-jwt-secret-integration"
os.environ["CSRF_TOKEN_SECRET"] = "test-csrf-secret-integration"
os.environ["ENV"] = "development"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"


@pytest.fixture
def client():
    from core.api_fast import app

    with TestClient(app) as test_client:
        yield test_client


class TestNewsletterUnsubscribeSecurity:
    def test_rejects_missing_token(self, client):
        response = client.get("/api/newsletter/unsubscribe?lang=sr")
        assert response.status_code == 422

    def test_rejects_invalid_token(self, client):
        response = client.get("/api/newsletter/unsubscribe?token=not-valid&lang=sr")
        assert response.status_code == 400


class TestHealthEndpointExposure:
    @patch("core.api_fast._is_trusted_ops_client", return_value=False)
    def test_public_health_omits_celery_queue(self, _mock_trusted, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "database" in data
        assert "redis" in data
        assert "celery_queue" not in data
        assert "synthesis_quality" not in data

    def test_localhost_health_includes_ops_fields(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "celery_queue" in data
        assert "synthesis_quality" in data


class TestDeliveryTrackingSecurity:
    def test_rejects_missing_token(self, client):
        response = client.get("/api/delivery/track/click?event_id=1&redirect=/briefing", follow_redirects=False)
        assert response.status_code == 422

    def test_rejects_invalid_token(self, client):
        response = client.get(
            "/api/delivery/track/click?event_id=1&redirect=/briefing&token=bad",
            follow_redirects=False,
        )
        assert response.status_code == 400


class TestCsrfProtection:
    def test_post_without_token_is_rejected(self, client):
        response = client.post("/api/profile/sync/init")
        assert response.status_code == 403
        assert response.json()["detail"] == "Nevaliden CSRF token"

    def test_post_rejects_header_cookie_mismatch(self, client):
        token = generate_csrf_token()
        client.cookies.set("csrf_token", f"{token}-mismatch")
        response = client.post(
            "/api/profile/sync/init",
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Nevaliden CSRF token"

    def test_csrf_token_endpoint_returns_valid_token(self, client):
        response = client.get("/api/csrf-token")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "success"
        assert payload["csrf_token"]


class TestCorsPolicy:
    def test_get_includes_allowed_origin(self, client):
        response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_get_omits_origin_for_unknown_site(self, client):
        response = client.get("/api/health", headers={"Origin": "https://evil.example"})
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers
