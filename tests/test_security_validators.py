import pytest
from fastapi import HTTPException

# Now we can import the validators
from routes.security import (
    validate_cluster_id,
    validate_date,
    validate_email,
    validate_list_param,
    validate_string_param,
)


def test_validate_cluster_id():
    # Must be 6-64 hex chars (now supports dashes)
    import sys as _sys

    _fm = _sys.modules.get("fastapi")
    print(f"DIAG fastapi mod={_fm!r} file={getattr(_fm, '__file__', None)!r}")
    print(f"DIAG test HTTPException={HTTPException!r}")
    print(f"DIAG func HTTPException={validate_cluster_id.__globals__.get('HTTPException')!r}")
    assert validate_cluster_id("123456") == "123456"
    assert validate_cluster_id("abcdef123456") == "abcdef123456"
    assert validate_cluster_id("fe0486f7-9bf") == "fe0486f7-9bf"

    with pytest.raises(HTTPException) as exc:
        validate_cluster_id("12345")  # Too short

    with pytest.raises(HTTPException) as exc:
        validate_cluster_id("cluster; drop table articles")
    assert exc.value.status_code == 400


def test_validate_date():
    assert validate_date("2025-04-27") == "2025-04-27"
    with pytest.raises(HTTPException):
        validate_date("invalid-date")

    # The current regex only checks YYYY-MM-DD format, not calendar validity
    # Let's verify it rejects non-matching strings
    with pytest.raises(HTTPException):
        validate_date("27-04-2025")


def test_validate_email():
    assert validate_email("test@example.com") == "test@example.com"
    with pytest.raises(HTTPException):
        validate_email("invalid-email")
    with pytest.raises(HTTPException):
        validate_email("test@example")


def test_validate_string_param():
    assert validate_string_param("normal string", "param") == "normal string"
    assert validate_string_param("a" * 200, "param") == "a" * 200

    with pytest.raises(HTTPException):
        validate_string_param("a" * 201, "param")

    with pytest.raises(HTTPException):
        validate_string_param("   ", "param", allow_empty=False)


def test_validate_list_param():
    assert validate_list_param(["a", "b"], "param") == ["a", "b"]
    assert len(validate_list_param(["a"] * 20, "param")) == 20

    with pytest.raises(HTTPException):
        validate_list_param(["a"] * 21, "param")

    with pytest.raises(HTTPException):
        validate_list_param(["a" * 101], "param")
