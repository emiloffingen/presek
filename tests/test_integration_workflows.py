import os
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-integration")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-integration")
os.environ.setdefault("CSRF_TOKEN_SECRET", "test-csrf-secret-integration")
os.environ.setdefault("ENV", "development")


@pytest.fixture
def client():
    from core.api_fast import app

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()


class TestSecurityMetricsIntegration:
    def test_security_status_endpoint_requires_auth(self, client):
        """Verify that the /api/security/status endpoint denies unauthorized requests."""
        response = client.get("/api/security/status")
        # admin_auth raises HTTPException 401/403 or returns error
        assert response.status_code in (401, 403)

    def test_security_status_endpoint_accepts_valid_jwt(self, client):
        """Verify that the /api/security/status endpoint returns monitoring status with a valid token."""
        from core.auth import create_admin_jwt

        token = create_admin_jwt()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Mock run_comprehensive_check to return a simulated response to avoid executing actual sub processes
        mock_result = {
            "status": "healthy",
            "timestamp": "2026-06-29T12:00:00",
            "issues": 0,
            "warnings": 1,
            "info": 5,
            "details": {
                "issues": [],
                "warnings": [{"category": "Dependencies", "message": "Test warning", "severity": "warning"}],
                "info": []
            }
        }
        
        with patch("scripts.security_monitoring.SecurityMonitor.run_comprehensive_check", return_value=mock_result):
            response = client.get("/api/security/status", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert data["issues"] == 0
            assert len(data["details"]["warnings"]) == 1

    def test_version_prefixed_security_status_endpoint(self, client):
        """Verify version prefixed route works identically."""
        from core.auth import create_admin_jwt

        token = create_admin_jwt()
        headers = {"Authorization": f"Bearer {token}"}
        
        mock_result = {"status": "healthy", "issues": 0}
        with patch("scripts.security_monitoring.SecurityMonitor.run_comprehensive_check", return_value=mock_result):
            response = client.get("/api/v1/security/status", headers=headers)
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"
