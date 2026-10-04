import asyncio
import json

from core.api_fast import get_csrf_token, version_info


def test_api_critical_handlers():
    """
    Smoke test critical lightweight endpoint handlers without requiring a live server.
    """
    csrf_response = get_csrf_token()
    csrf_payload = json.loads(csrf_response.body)
    version_payload = asyncio.run(version_info())

    assert csrf_payload["status"] == "success"
    assert csrf_payload["csrf_token"]
    # The cookie must carry the same token so the double-submit check matches.
    assert f"csrf_token={csrf_payload['csrf_token']}" in csrf_response.headers["set-cookie"]
    assert "version" in version_payload


def test_version_check_responds():
    response = asyncio.run(version_info())
    assert "version" in response
