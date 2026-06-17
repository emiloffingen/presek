"""Consistent API error payloads and helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

ERROR_STATUS = "error"
SUCCESS_STATUS = "success"


def api_error_payload(
    message: str,
    *,
    detail: Any = None,
    code: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": ERROR_STATUS}
    if message:
        payload["message"] = message
        payload["detail"] = detail if detail is not None else message
    elif detail is not None:
        payload["detail"] = detail
    if code:
        payload["code"] = code
    payload.update(extra)
    return payload


def soft_error(*, message: str = "", code: str | None = None, **extra: Any) -> dict[str, Any]:
    """Graceful error body for HTTP 200 responses (partial page failure)."""
    return api_error_payload(message, code=code, **extra)


def api_error_response(
    message: str,
    status_code: int,
    *,
    detail: Any = None,
    code: str | None = None,
    **extra: Any,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=api_error_payload(message, detail=detail, code=code, **extra),
    )


def raise_api_error(status_code: int, message: str, *, code: str | None = None) -> None:
    raise HTTPException(status_code=status_code, detail=message, headers={"X-Error-Code": code} if code else None)


def normalize_http_exception_content(detail: Any) -> dict[str, Any]:
    if isinstance(detail, str):
        return api_error_payload(detail)
    if isinstance(detail, list):
        return api_error_payload("Nevaliden baranie", detail=detail, code="validation_error")
    return api_error_payload(str(detail), detail=detail)


def rate_limit_payload(message: str, *, detail: str | None = None) -> dict[str, Any]:
    """429 payload shared by slowapi and custom middleware."""
    return api_error_payload(
        message,
        detail=detail or message,
        code="rate_limit_exceeded",
        error=message,
    )
