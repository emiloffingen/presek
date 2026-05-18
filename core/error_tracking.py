"""
error_tracking.py - Centralized error tracking and monitoring for Presek

Integrates with Sentry for production error monitoring and provides
local error logging for development.
"""

import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

# Configure logging
log = logging.getLogger("presek.error_tracking")

# Sentry configuration
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
ENVIRONMENT = os.environ.get("ENV", "development")

# Initialize Sentry only if configured
_sentry_initialized = False


def _initialize_sentry():
    """Initialize Sentry client if DSN is configured."""
    global _sentry_initialized

    if _sentry_initialized or not SENTRY_DSN:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_logging = LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR,  # Send errors as events
        )

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            integrations=[sentry_logging, FastApiIntegration()],
            traces_sample_rate=0.1,  # Sample 10% of transactions
            profiles_sample_rate=0.01,  # Sample 1% of transactions for profiling
            release=f"presek@{os.environ.get('APP_VERSION', 'dev')}",
            # Set a fixed sample rate for errors
            sample_rate=1.0 if ENVIRONMENT == "production" else 0.1,
        )

        log.info("Sentry error tracking initialized")
        _sentry_initialized = True
    except ImportError:
        log.warning("Sentry SDK not installed - error tracking disabled")
    except Exception as e:
        log.error(f"Failed to initialize Sentry: {e}")


def capture_exception(error: Exception, context: Optional[Dict[str, Any]] = None):
    """Capture an exception with optional context."""
    _initialize_sentry()

    if not _sentry_initialized:
        # Fallback to local logging
        log_error(error, context)
        return

    try:
        import sentry_sdk

        if context:
            with sentry_sdk.push_scope() as scope:
                for key, value in context.items():
                    scope.set_extra(key, value)
                sentry_sdk.capture_exception(error)
        else:
            sentry_sdk.capture_exception(error)
    except Exception as e:
        log.error(f"Failed to capture exception in Sentry: {e}")
        log_error(error, context)


def capture_message(message: str, level: str = "error", context: Optional[Dict[str, Any]] = None):
    """Capture a custom message with optional context."""
    _initialize_sentry()

    if not _sentry_initialized:
        log_level = getattr(logging, level.upper(), logging.ERROR)
        log.log(log_level, message, extra=context or {})
        return

    try:
        import sentry_sdk

        if context:
            with sentry_sdk.push_scope() as scope:
                for key, value in context.items():
                    scope.set_extra(key, value)
                sentry_sdk.capture_message(message, level=level)
        else:
            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        log.error(f"Failed to capture message in Sentry: {e}")
        log_level = getattr(logging, level.upper(), logging.ERROR)
        log.log(log_level, message, extra=context or {})


def log_error(error: Exception, context: Optional[Dict[str, Any]] = None):
    """Log an error with context to local logs."""
    error_data = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "timestamp": datetime.utcnow().isoformat(),
    }

    if context:
        error_data["context"] = context

    # Include traceback in debug mode
    if os.environ.get("DEBUG", "false").lower() == "true":
        error_data["traceback"] = traceback.format_exc()

    log.error(f"Error occurred: {error_data}")


def set_user_context(user_id: str, email: Optional[str] = None, **kwargs):
    """Set user context for error tracking."""
    _initialize_sentry()

    if not _sentry_initialized:
        return

    try:
        import sentry_sdk

        sentry_sdk.set_user({"id": user_id, "email": email, **kwargs})
    except Exception as e:
        log.error(f"Failed to set user context in Sentry: {e}")


def add_breadcrumb(message: str, category: str = "default", data: Optional[Dict[str, Any]] = None):
    """Add a breadcrumb for diagnostic context."""
    _initialize_sentry()

    if not _sentry_initialized:
        log.debug(f"Breadcrumb: {message}", extra=data or {})
        return

    try:
        import sentry_sdk

        breadcrumb_data = {"message": message, "category": category, "level": "info"}

        if data:
            breadcrumb_data["data"] = data

        sentry_sdk.add_breadcrumb(breadcrumb_data)
    except Exception as e:
        log.error(f"Failed to add breadcrumb in Sentry: {e}")


def start_transaction(name: str, operation: str = "default"):
    """Start a transaction for performance monitoring."""
    _initialize_sentry()

    if not _sentry_initialized:
        log.debug(f"Transaction started: {name}")
        return None

    try:
        import sentry_sdk

        return sentry_sdk.start_transaction(name=name, op=operation)
    except Exception as e:
        log.error(f"Failed to start transaction in Sentry: {e}")
        return None


def configure_error_tracking():
    """Configure error tracking for the application."""
    _initialize_sentry()

    # Set up global exception handler
    import sys

    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        capture_exception(exc_value, {"type": str(exc_type), "uncaught": True})

        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_uncaught_exception

    log.info("Error tracking configured")


# Initialize error tracking when module is imported
configure_error_tracking()
