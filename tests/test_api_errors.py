"""Tests for unified API error helpers."""

import pytest
from fastapi import HTTPException

from core.api_errors import (
    api_error_payload,
    api_error_response,
    normalize_http_exception_content,
    rate_limit_payload,
    soft_error,
)


def test_api_error_payload_includes_message_and_detail():
    payload = api_error_payload("Nevaliden JSON")
    assert payload == {
        "status": "error",
        "message": "Nevaliden JSON",
        "detail": "Nevaliden JSON",
    }


def test_soft_error_allows_extra_fields_without_message():
    payload = soft_error(clusters=[])
    assert payload["status"] == "error"
    assert payload["clusters"] == []
    assert "message" not in payload


def test_normalize_http_exception_content_for_validation_list():
    payload = normalize_http_exception_content([{"loc": ["q"], "msg": "required", "type": "missing"}])
    assert payload["status"] == "error"
    assert payload["code"] == "validation_error"
    assert isinstance(payload["detail"], list)


def test_api_error_response_status_code():
    response = api_error_response("Not found", 404, code="not_found")
    assert response.status_code == 404
    assert response.body.decode() == (
        '{"status":"error","message":"Not found","detail":"Not found","code":"not_found"}'
    )


def test_rate_limit_payload_keeps_legacy_error_key():
    payload = rate_limit_payload("Premnogu baranja", detail="5/minute")
    assert payload["status"] == "error"
    assert payload["error"] == "Premnogu baranja"
    assert payload["code"] == "rate_limit_exceeded"


def test_raise_api_error():
    with pytest.raises(HTTPException) as exc_info:
        from core.api_errors import raise_api_error

        raise_api_error(403, "Neovlasten pristap")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Neovlasten pristap"
