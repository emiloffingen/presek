import asyncio

from core.api_fast import get_csrf_token, version_info


def test_api_critical_handlers():
    """
    Smoke test critical lightweight endpoint handlers without requiring a live server.
    """
    csrf_payload = get_csrf_token()
    version_payload = asyncio.run(version_info())

    assert csrf_payload["status"] == "success"
    assert csrf_payload["csrf_token"]
    assert "version" in version_payload

def test_version_check_responds():
    response = asyncio.run(version_info())
    assert "version" in response
