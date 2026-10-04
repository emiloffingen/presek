"""HTTP-level security regression tests."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from routes.security import generate_csrf_token

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-integration")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-integration")
os.environ.setdefault("CSRF_TOKEN_SECRET", "test-csrf-secret-integration")
os.environ.setdefault("ENV", "development")
os.environ["CORS_ORIGINS"] = "http://localhost:3000"


@pytest.fixture
def client():
    from core.api_fast import app

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()


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
        assert response.json()["detail"] == "Невалиден CSRF токен"

    def test_post_rejects_header_cookie_mismatch(self, client):
        token = generate_csrf_token()
        client.cookies.set("csrf_token", f"{token}-mismatch")
        response = client.post(
            "/api/profile/sync/init",
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Невалиден CSRF токен"

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


class TestNewsletterDoubleOptIn:
    @staticmethod
    def _route_globals(client, path):
        # Patch the module the mounted endpoint actually closes over; other tests
        # may re-import routes.stats, leaving a different object in sys.modules.
        for route in client.app.routes:
            router = getattr(route, "original_router", None)
            candidates = router.routes if router is not None else [route]
            for candidate in candidates:
                if getattr(candidate, "path", None) in {path, path.removeprefix("/api")}:
                    return candidate.endpoint.__globals__
        raise AssertionError(f"route {path} not mounted")

    @staticmethod
    def _fake_db(existing=None):
        from unittest.mock import AsyncMock, MagicMock

        fake = MagicMock()
        fake.async_execute_one = AsyncMock(return_value=existing)
        fake.async_execute = AsyncMock(return_value=None)
        return fake

    def _subscribe(self, client, email="reader@example.com"):
        token = generate_csrf_token()
        client.cookies.set("csrf_token", token)
        return client.post(
            "/api/newsletter/subscribe",
            json={"email": email, "locale": "mk"},
            headers={"X-CSRF-Token": token},
        )

    def test_new_address_is_stored_inactive_and_emailed(self, client):
        fake = self._fake_db(existing=None)
        send = MagicMock(return_value=True)
        g = self._route_globals(client, "/api/newsletter/subscribe")
        with patch.dict(g, {"db": fake, "_send_newsletter_confirmation": send}):
            response = self._subscribe(client)

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        send.assert_called_once_with("reader@example.com", "mk")
        insert_sql, insert_params = fake.async_execute.call_args.args[:2]
        assert "is_active" in insert_sql and "FALSE" in insert_sql
        assert insert_params == ("reader@example.com", "mk")

    def test_active_address_gets_same_answer_without_email(self, client):
        fake = self._fake_db(existing={"is_active": True})
        send = MagicMock(return_value=True)
        g = self._route_globals(client, "/api/newsletter/subscribe")
        with patch.dict(g, {"db": fake, "_send_newsletter_confirmation": send}):
            response = self._subscribe(client)

        assert response.json()["status"] == "success"
        send.assert_not_called()
        fake.async_execute.assert_not_called()

    def test_confirm_activates_with_valid_token_only(self, client):
        from core.signed_tokens import build_newsletter_confirm_token, build_newsletter_unsubscribe_token

        fake = self._fake_db()
        with patch.dict(self._route_globals(client, "/api/newsletter/confirm"), {"db": fake}):
            bad = client.get("/api/newsletter/confirm", params={"token": "nope", "lang": "mk"})
            wrong_kind = client.get(
                "/api/newsletter/confirm",
                params={"token": build_newsletter_unsubscribe_token("reader@example.com", "mk"), "lang": "mk"},
            )
            assert fake.async_execute.call_count == 0
            ok = client.get(
                "/api/newsletter/confirm",
                params={"token": build_newsletter_confirm_token("reader@example.com", "mk"), "lang": "mk"},
            )

        assert bad.status_code == 400
        assert wrong_kind.status_code == 400
        assert ok.status_code == 200
        sql, params = fake.async_execute.call_args.args[:2]
        assert "is_active = TRUE" in sql
        assert params == ("reader@example.com", "mk")
