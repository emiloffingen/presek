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
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from fastapi import HTTPException, Path, Query
from pydantic import BaseModel, ValidationError, field_validator

from core.api_errors import soft_error


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
    r"(?:/?|[/?]\S+)$", re.IGNORECASE
)

class QueryParams(BaseModel):
    """Base model for query parameter validation."""
    pass

class PaginationParams(BaseModel):
    """Validation model for pagination parameters."""
    page: int = Query(1, ge=1, le=1000, description="Page number")
    limit: int = Query(20, ge=5, le=100, description="Items per page")
    
    @field_validator('page')
    @classmethod
    def validate_page(cls, v):
        if v < 1 or v > 1000:
            raise ValueError('Page must be between 1 and 1000')
        return v
    
    @field_validator('limit')
    @classmethod
    def validate_limit(cls, v):
        if v < 5 or v > 100:
            raise ValueError('Limit must be between 5 and 100')
        return v

class SearchParams(BaseModel):
    """Validation model for search parameters."""
    q: str = Query("", max_length=500, description="Search query")
    lang: Optional[str] = Query(None, max_length=2, description="Language code")
    
    @field_validator('q')
    @classmethod
    def validate_search_query(cls, v):
        if len(v) > 500:
            raise ValueError('Search query too long (max 500 characters)')
        # Basic XSS prevention
        if any(tag in v.lower() for tag in ['<script>', '</script>', 'javascript:', 'onerror=']):
            raise ValueError('Invalid characters in search query')
        return v

class ClusterIDParam(BaseModel):
    """Validation model for cluster ID parameters."""
    cluster_id: str = Path(..., description="Cluster UUID")
    
    @field_validator('cluster_id')
    @classmethod
    def validate_cluster_id(cls, v):
        if not CLUSTER_ID_PATTERN.match(v):
            raise ValueError('Invalid cluster ID format')
        return v

class ArticleIDParam(BaseModel):
    """Validation model for article ID parameters."""
    article_id: str = Path(..., description="Article UUID")
    
    @field_validator('article_id')
    @classmethod
    def validate_article_id(cls, v):
        if not ARTICLE_ID_PATTERN.match(v):
            raise ValueError('Invalid article ID format')
        return v

class SourceNameParam(BaseModel):
    """Validation model for source name parameters."""
    source: str = Query(..., max_length=50, description="Source name")
    
    @field_validator('source')
    @classmethod
    def validate_source_name(cls, v):
        if not SOURCE_NAME_PATTERN.match(v):
            raise ValueError('Invalid source name format')
        return v

class EmailParam(BaseModel):
    """Validation model for email parameters."""
    email: str = Query(..., max_length=254, description="Email address")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not EMAIL_PATTERN.match(v):
            raise ValueError('Invalid email format')
        return v

class URLParam(BaseModel):
    """Validation model for URL parameters."""
    url: str = Query(..., max_length=2048, description="URL")
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if len(v) > 2048:
            raise ValueError('URL too long (max 2048 characters)')
        if not URL_PATTERN.match(v):
            raise ValueError('Invalid URL format')
        
        # Additional URL validation
        try:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError('Invalid URL format')
        except Exception:
            raise ValueError('Invalid URL format')
        
        return v

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
        raise HTTPException(status_code=400, detail=f"Search query too long (max {max_length} characters)")
    
    # Basic XSS prevention
    if any(tag in q.lower() for tag in ['<script>', '</script>', 'javascript:', 'onerror=']):
        raise HTTPException(status_code=400, detail="Invalid characters in search query")
    
    return q

def validate_pagination(page: int = 1, limit: int = 20, max_page: int = 1000, max_limit: int = 100) -> tuple:
    """Validate pagination parameters."""
    try:
        page = int(page)
        limit = int(limit)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid pagination parameters")
    
    if page < 1 or page > max_page:
        raise HTTPException(status_code=400, detail=f"Page must be between 1 and {max_page}")
    
    if limit < 5 or limit > max_limit:
        raise HTTPException(status_code=400, detail=f"Limit must be between 5 and {max_limit}")
    
    return page, limit

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

def validate_language_code(lang: str, allowed_languages: List[str] = None) -> str:
    """Validate a language code parameter."""
    if allowed_languages is None:
        allowed_languages = ['sr', 'mk', 'en']
    
    if not lang or not isinstance(lang, str):
        return None
    
    lang = lang.lower().strip()
    
    if len(lang) != 2:
        raise HTTPException(status_code=400, detail="Language code must be 2 characters")
    
    if lang not in allowed_languages:
        raise HTTPException(status_code=400, detail=f"Language must be one of: {', '.join(allowed_languages)}")
    
    return lang

def validate_boolean_param(value: Union[bool, str]) -> bool:
    """Validate a boolean parameter from various input types."""
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        value = value.lower().strip()
        if value in ('true', '1', 'yes', 'on'):
            return True
        elif value in ('false', '0', 'no', 'off'):
            return False
    
    raise HTTPException(status_code=400, detail="Invalid boolean value")

def validate_request_body(body: Dict[str, Any], required_fields: List[str] = None, max_size: int = 10000) -> Dict[str, Any]:
    """Validate a request body."""
    if not body or not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid request body")
    
    # Check size
    try:
        body_str = str(body)
        if len(body_str) > max_size:
            raise HTTPException(status_code=400, detail=f"Request body too large (max {max_size} characters)")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    
    # Check required fields
    if required_fields:
        missing_fields = [field for field in required_fields if field not in body]
        if missing_fields:
            raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing_fields)}")
    
    return body

def sanitize_html_input(text: str, max_length: int = 1000) -> str:
    """Sanitize HTML input to prevent XSS attacks."""
    if not text or not isinstance(text, str):
        return text
    
    if len(text) > max_length:
        raise HTTPException(status_code=400, detail=f"Text too long (max {max_length} characters)")
    
    # Basic HTML sanitization - remove script tags and dangerous attributes
    sanitized = text
    sanitized = re.sub(r'<script.*?>.*?</script>', '', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'on\w+\s*=', '', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'javascript:', '', sanitized, flags=re.IGNORECASE)
    
    return sanitized

def validate_api_key(api_key: str) -> str:
    """Validate an API key format."""
    if not api_key or not isinstance(api_key, str):
        raise HTTPException(status_code=400, detail="Invalid API key")
    
    if len(api_key) < 16 or len(api_key) > 128:
        raise HTTPException(status_code=400, detail="Invalid API key length")
    
    # Basic format validation
    if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
        raise HTTPException(status_code=400, detail="Invalid API key format")
    
    return api_key

class ValidationErrorResponse(BaseModel):
    """Standard validation error response."""
    status: str = "error"
    error: str = "validation_error"
    message: str
    details: Optional[Dict[str, Any]] = None

def handle_validation_error(e: ValidationError) -> Dict[str, Any]:
    """Handle Pydantic validation errors and return a standard response."""
    errors = []
    for error in e.errors():
        field = error.get('loc', ['unknown'])[-1]
        message = error.get('msg', 'Invalid value')
        errors.append(f"{field}: {message}")
    
    return ValidationErrorResponse(
        message="Validation failed",
        details={"errors": errors}
    ).dict()

# Request validation decorators

def validate_request_params(func):
    """Decorator to validate request parameters."""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            return handle_validation_error(e)
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"Unexpected validation error: {e}")
            return soft_error(message="Internal validation error")
    
    return wrapper

# Input sanitization functions

def sanitize_search_query(query: str) -> str:
    """Sanitize search query to prevent injection attacks."""
    if not query:
        return query
    
    # Remove potential SQL injection patterns
    dangerous_patterns = [
        r'\b(DROP|DELETE|INSERT|UPDATE|SELECT)\b',
        r'--',
        r';',
        r'/\*',
        r'\*/',
        r'\b(OR|AND)\b\s+\d+\s*=\s*\d+',
        r'\b(UNION|JOIN)\b',
        r'\b(EXEC|EXECUTE)\b',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            raise HTTPException(status_code=400, detail="Invalid search query")
    
    return query.strip()

# Initialize validation system
def init_validation_system():
    """Initialize the validation system."""
    log.info("Input validation system initialized")

# Auto-initialize
init_validation_system()