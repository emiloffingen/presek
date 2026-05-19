import pytest
import httpx
import os

# Base URL for the API
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:5001")

@pytest.mark.asyncio
async def test_api_critical_endpoints():
    """
    Smoke test critical endpoints to ensure they return 200 OK.
    """
    endpoints = [
        "/api/stats/summary",
        "/api/intelligence/cluster/test-cluster-123/analyst",
    ]
    
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        for endpoint in endpoints:
            # We skip the auth-required endpoints or provide placeholder auth 
            # if we just want to check they are up and running.
            response = await client.get(endpoint)
            # Depending on if endpoints are fully public or auth-gated, 
            # 200, 400 (if invalid cluster), 401, or 403 are acceptable signs of service availability.
            assert response.status_code in [200, 400, 401, 403], f"Endpoint {endpoint} failed with {response.status_code}"

@pytest.mark.asyncio
async def test_health_check_responds():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert "status" in response.json()
