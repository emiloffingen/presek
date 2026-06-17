"""HTTP-level security regression tests."""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-integration")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-integration")
os.environ.setdefault("CSRF_TOKEN_SECRET", "test-csrf-secret-integration")
os.environ.setdefault("ENV", "development")


@pytest.fixture(scope="module")
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
