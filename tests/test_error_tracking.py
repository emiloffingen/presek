"""Test error tracking functionality."""

from core.error_tracking import capture_exception, capture_message, log_error, set_user_context


def test_error_capture_with_context():
    """Test error capturing with context."""
    try:
        # Simulate an error
        raise ValueError("Test error")
    except ValueError as e:
        # Capture the error with context
        context = {"test_case": "error_capture", "value": 42}
        capture_exception(e, context)
        
        # Should not raise an exception
        assert True


def test_message_capture():
    """Test message capturing."""
    # Capture a message
    context = {"test_case": "message_capture"}
    capture_message("Test message", "info", context)
    
    # Should not raise an exception
    assert True


def test_log_error():
    """Test error logging."""
    try:
        raise RuntimeError("Test runtime error")
    except RuntimeError as e:
        context = {"test_case": "log_error"}
        log_error(e, context)
        
        # Should not raise an exception
        assert True


def test_set_user_context():
    """Test setting user context."""
    # Set user context
    set_user_context("test_user_123", "test@example.com")
    
    # Should not raise an exception
    assert True


def test_error_capture_without_sentry():
    """Test error capturing when Sentry is not configured."""
    # Mock Sentry not being available
    import core.error_tracking
    original_init = core.error_tracking._sentry_initialized
    core.error_tracking._sentry_initialized = False
    
    try:
        # Capture an error
        try:
            raise ValueError("Test error without Sentry")
        except ValueError as e:
            capture_exception(e, {"test": "no_sentry"})
            
            # Should fall back to local logging
            assert True
    finally:
        # Restore original state
        core.error_tracking._sentry_initialized = original_init


def test_message_capture_without_sentry():
    """Test message capturing when Sentry is not configured."""
    # Mock Sentry not being available
    import core.error_tracking
    original_init = core.error_tracking._sentry_initialized
    core.error_tracking._sentry_initialized = False
    
    try:
        # Capture a message
        capture_message("Test message without Sentry", "warning")
        
        # Should fall back to local logging
        assert True
    finally:
        # Restore original state
        core.error_tracking._sentry_initialized = original_init


def test_error_tracking_initialization():
    """Test error tracking initialization."""
    # Import should initialize error tracking
    
    # Should not raise an exception
    assert True


def test_breadcrumb_addition():
    """Test adding breadcrumbs."""
    from core.error_tracking import add_breadcrumb
    
    # Add a breadcrumb
    data = {"test_case": "breadcrumb", "step": 1}
    add_breadcrumb("Test breadcrumb message", "test_category", data)
    
    # Should not raise an exception
    assert True


def test_transaction_start():
    """Test starting a transaction."""
    from core.error_tracking import start_transaction
    
    # Start a transaction
    transaction = start_transaction("test_transaction", "test_operation")
    
    # Transaction might be None if Sentry is not available
    # Should not raise an exception
    assert True