"""
input_validation.py - Comprehensive input validation utilities

Provides validation functions for:
- Query parameters
- Path parameters
- Request bodies
- Security headers
- Rate limiting
"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError


def get_logger(name: str) -> logging.Logger:
    """Get a logger with consistent configuration."""
    return logging.getLogger(name)


log = get_logger("presek.validation")


# Common validation patterns
CLUSTER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")
ARTICLE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")
SOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9\s\-_.]{2,50}$")
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
URL_PATTERN = re.compile(
    r"^(https?|ftp)://"  # scheme
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain
    r"localhost|"  # localhost
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ip
    r"(?:\:\d+)?"  # port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


def validate_cluster_id(cluster_id: str) -> str:
    """Validate a cluster ID parameter."""
    if not cluster_id or not isinstance(cluster_id, str):
        raise HTTPException(status_code=400, detail="Invalid cluster ID")

    if not CLUSTER_ID_PATTERN.match(cluster_id):
        raise HTTPException(status_code=400, detail="Invalid cluster ID format")

    return cluster_id


def validate_article_id(article_id: str) -> str:
    """Validate an article ID parameter."""
    if not article_id or not isinstance(article_id, str):
        raise HTTPException(status_code=400, detail="Invalid article ID")

    if not ARTICLE_ID_PATTERN.match(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID format")

    return article_id


def validate_source_name(source: str) -> str:
    """Validate a source name parameter."""
    if not source or not isinstance(source, str):
        raise HTTPException(status_code=400, detail="Invalid source name")

    if len(source) > 50:
        raise HTTPException(status_code=400, detail="Source name too long")

    if not SOURCE_NAME_PATTERN.match(source):
        raise HTTPException(status_code=400, detail="Invalid source name format")

    return source


def validate_search_query(q: str, max_length: int = 500) -> str:
    """Validate a search query parameter."""
    if not q or not isinstance(q, str):
        return q  # Empty query is allowed

    if len(q) > max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Search query too long (max {max_length} characters)",
        )

    # Basic XSS prevention
    if any(tag in q.lower() for tag in ["<script>", "</script>", "javascript:", "onerror="]):
        raise HTTPException(status_code=400, detail="Invalid characters in search query")

    return q


def validate_email(email: str) -> str:
    """Validate an email address."""
    if not email or not isinstance(email, str):
        raise HTTPException(status_code=400, detail="Invalid email")

    if len(email) > 254:
        raise HTTPException(status_code=400, detail="Email too long")

    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    return email


def validate_url(url: str, max_length: int = 2048) -> str:
    """Validate a URL."""
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=400, detail="Invalid URL")

    if len(url) > max_length:
        raise HTTPException(status_code=400, detail=f"URL too long (max {max_length} characters)")

    if not URL_PATTERN.match(url):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    # Additional URL validation
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Invalid URL format")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    return url


def validate_language_code(lang: str, allowed_languages: list[str] = None) -> str:
    """Validate a language code parameter."""
    if allowed_languages is None:
        allowed_languages = ["sr", "mk", "en"]

    if not lang or not isinstance(lang, str):
        return None

    lang = lang.lower().strip()

    if len(lang) != 2:
        raise HTTPException(status_code=400, detail="Language code must be 2 characters")

    if lang not in allowed_languages:
        raise HTTPException(
            status_code=400,
            detail=f"Language must be one of: {', '.join(allowed_languages)}",
        )

    return lang


class ValidationErrorResponse(BaseModel):
    """Standard validation error response."""

    status: str = "error"
    error: str = "validation_error"
    message: str
    details: dict[str, Any] | None = None


def handle_validation_error(e: ValidationError) -> dict[str, Any]:
    """Handle Pydantic validation errors and return a standard response."""
    errors = []
    for error in e.errors():
        field = error.get("loc", ["unknown"])[-1]
        message = error.get("msg", "Invalid value")
        errors.append(f"{field}: {message}")

    return ValidationErrorResponse(message="Validation failed", details={"errors": errors}).dict()


# Request validation decorators


# Input sanitization functions


# Initialize validation system
def init_validation_system():
    """Initialize the validation system."""
    log.info("Input validation system initialized")


# Auto-initialize
init_validation_system()
