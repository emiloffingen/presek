"""
logging_config.py - Centralized logging configuration for Presek

Provides structured logging with JSON output for production and
human-readable console output for development.

Usage:
    from logging_config import get_logger, setup_logging
    
    # At application startup
    setup_logging()
    
    # In modules
    logger = get_logger("module_name")
    logger.info("message", extra={"key": "value"})
"""

import os
import sys
import logging
import json
from typing import Dict, Any, Optional


# =============================================================================
# Configuration
# =============================================================================


def _get_log_level() -> int:
    """Get log level from environment or default to INFO."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level, logging.INFO)


def _get_log_format() -> str:
    """Get log format from environment. Default to 'json' in production."""
    env = os.environ.get("ENV", "development")
    if env == "production":
        return "json"
    return os.environ.get("LOG_FORMAT", "text")


# =============================================================================
# Structured Log Formatter
# =============================================================================


class StructuredFormatter(logging.Formatter):
    """Formatter that outputs log records as JSON for structured logging."""

    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add stack info if present
        if record.stack_info:
            log_data["stack_info"] = self.formatStack(record.stack_info)

        # Include extra fields
        if self.include_extra and hasattr(record, "extra_data") and record.extra_data:
            log_data.update(record.extra_data)

        # Always include these standard fields
        for attr in (
            "module",
            "funcName",
            "lineno",
            "processName",
            "threadName",
            "process",
            "thread",
        ):
            value = getattr(record, attr, None)
            if value:
                log_data[attr] = value

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    def format(self, record: logging.LogRecord) -> str:
        # Check for extra data
        extra_str = ""
        if hasattr(record, "extra_data") and record.extra_data:
            extra_str = " | " + " ".join(
                f"{k}={v}" for k, v in record.extra_data.items()
            )

        return super().format(record) + extra_str


# =============================================================================
# Custom Logger with Extra Data Support
# =============================================================================


class PresekLogger(logging.Logger):
    """Logger that supports extra structured data."""

    def __init__(self, name: str, level: int = logging.NOTSET):
        super().__init__(name, level)
        self.extra_data: Optional[Dict[str, Any]] = None

    def _log(self, level: int, msg: str, args: tuple, **kwargs) -> None:
        # Extract extra data from kwargs
        self.extra_data = kwargs.pop("extra", None)
        super()._log(level, msg, args, **kwargs)
        self.extra_data = None


# =============================================================================
# Setup Functions
# =============================================================================


def setup_logging() -> None:
    """
    Configure logging for the application.

    Sets up structured JSON logging in production and
    human-readable logging in development.
    """
    log_format = _get_log_format()
    log_level = _get_log_level()

    # Create formatter based on format choice
    if log_format == "json":
        formatter = StructuredFormatter()
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
    else:
        # Text format for development
        formatter = TextFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    # Add our handler
    root_logger.addHandler(handler)

    # Set up module-specific loggers
    _setup_module_loggers()

    # Prevent propagation to root for prefixed loggers
    # This allows module-level control
    logging.getLogger("presek").propagate = True


def _setup_module_loggers() -> None:
    """Set up specific loggers for different modules with appropriate levels."""
    # Quiet noisy libraries in production
    if _get_log_format() == "json":
        libraries = [
            "urllib3",
            "httpx",
            "httpcore",
            "requests",
            "celery",
            "kombu",
            "amqp",
            "redis",
            "psycopg2",
            "sqlalchemy",
            "Pillow",
            "PIL",
            "torch",
            "transformers",
            "sentence_transformers",
        ]
        for lib in libraries:
            logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> PresekLogger:
    """
    Get a logger instance with support for structured extra data.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("User login", extra={"user_id": 123, "action": "login"})
    """
    logger = logging.getLogger(name)

    # Replace with our custom class if not already replaced
    if not isinstance(logger, PresekLogger):
        custom_logger = PresekLogger(name, logger.level)
        custom_logger.handlers = logger.handlers
        custom_logger.parent = logger.parent
        custom_logger.propagate = logger.propagate
        logging.Logger.manager.loggerDict[name] = custom_logger
        return custom_logger

    return logger


# =============================================================================
# Convenience Functions
# =============================================================================


def log_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an HTTP request with structured data."""
    data = {
        "http_method": method,
        "http_path": path,
        "http_status": status_code,
        "duration_ms": round(duration_ms, 2),
    }
    if client_ip:
        data["client_ip"] = client_ip
    if user_agent:
        data["user_agent"] = user_agent
    if extra:
        data.update(extra)

    if status_code >= 500:
        logger.error("Request failed", extra=data)
    elif status_code >= 400:
        logger.warning("Request warning", extra=data)
    else:
        logger.info("Request completed", extra=data)


def log_error(
    logger: logging.Logger, error: Exception, context: Optional[Dict[str, Any]] = None
) -> None:
    """Log an error with context."""
    data = {
        "error_type": type(error).__name__,
        "error_message": str(error),
    }
    if context:
        data["context"] = context
    logger.error("Error occurred", extra=data)


# =============================================================================
# Early Setup (called before imports)
# =============================================================================


def early_setup() -> None:
    """
    Minimal early logging setup for use before full initialization.
    Should be called at the very start of the application.
    """
    log_level = _get_log_level()

    # Set up a basic handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    # Use a simple formatter initially
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Perform early setup
# Note: This is called at module import time to ensure logging is available
# even before the application fully initializes
early_setup()
