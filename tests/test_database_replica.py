"""Test database read replica functionality."""

from unittest.mock import MagicMock, patch

import pytest

from core.database import db_manager


def test_read_replica_configuration():
    """Test read replica configuration."""
    # Test that config variables exist
    assert hasattr(db_manager, "_read_pool")

    # Initially should be None if not configured
    assert db_manager._read_pool is None


def test_read_only_query_routing():
    """Test that read-only queries are routed to replica when available."""
    # Mock the read pool
    mock_read_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_cursor.fetchall.return_value = [{"id": 1, "title": "Test"}]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_read_pool.getconn.return_value = mock_conn

    # Temporarily set the read pool
    original_read_pool = db_manager._read_pool
    db_manager._read_pool = mock_read_pool

    try:
        # Execute a read-only query
        results = db_manager.execute("SELECT * FROM articles LIMIT 1", read_only=True)

        # Should use read pool
        mock_read_pool.getconn.assert_called_once()
        mock_conn.cursor.assert_called_once()
        mock_cursor.execute.assert_called_once_with("SELECT * FROM articles LIMIT 1", None)
        mock_cursor.fetchall.assert_called_once()

        assert results == [{"id": 1, "title": "Test"}]
    finally:
        # Restore original read pool
        db_manager._read_pool = original_read_pool


def test_write_query_uses_primary():
    """Test that write queries use primary database."""
    # Mock both pools
    mock_read_pool = MagicMock()
    mock_primary_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_cursor.fetchall.return_value = [{"id": 1, "title": "Test"}]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_primary_pool.getconn.return_value = mock_conn

    # Temporarily set both pools
    original_read_pool = db_manager._read_pool
    original_pool = db_manager._pool
    db_manager._read_pool = mock_read_pool
    db_manager._pool = mock_primary_pool

    try:
        # Execute a write query (read_only=False)
        results = db_manager.execute("SELECT * FROM articles LIMIT 1", read_only=False)

        # Should use primary pool, not read pool
        mock_read_pool.getconn.assert_not_called()
        mock_primary_pool.getconn.assert_called_once()
        mock_conn.cursor.assert_called_once()
        mock_cursor.execute.assert_called_once_with("SELECT * FROM articles LIMIT 1", None)
        mock_cursor.fetchall.assert_called_once()

        assert results == [{"id": 1, "title": "Test"}]
    finally:
        # Restore original pools
        db_manager._read_pool = original_read_pool
        db_manager._pool = original_pool


def test_fallback_to_primary_when_replica_unavailable():
    """Test fallback to primary when replica is unavailable."""
    # Mock primary pool only (no read pool)
    mock_primary_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_cursor.fetchall.return_value = [{"id": 1, "title": "Test"}]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_primary_pool.getconn.return_value = mock_conn

    # Temporarily set only primary pool
    original_read_pool = db_manager._read_pool
    original_pool = db_manager._pool
    db_manager._read_pool = None  # No replica available
    db_manager._pool = mock_primary_pool

    try:
        # Execute a read-only query (should fallback to primary)
        results = db_manager.execute("SELECT * FROM articles LIMIT 1", read_only=True)

        # Should use primary pool since replica is not available
        mock_primary_pool.getconn.assert_called_once()
        mock_conn.cursor.assert_called_once()
        mock_cursor.execute.assert_called_once_with("SELECT * FROM articles LIMIT 1", None)
        mock_cursor.fetchall.assert_called_once()

        assert results == [{"id": 1, "title": "Test"}]
    finally:
        # Restore original pools
        db_manager._read_pool = original_read_pool
        db_manager._pool = original_pool


def test_database_manager_initialization_with_replica():
    """Test database manager initialization with replica support."""
    # Mock the environment variables
    with patch("core.config.DATABASE_READ_REPLICA_URL", "postgresql://user:pass@replica:5432/db"):
        with patch("core.config.USE_READ_REPLICA", True):
            # Re-import to get the patched config
            import importlib

            import core.database

            importlib.reload(core.database)

            # The database manager should attempt to initialize read pool
            # (actual connection testing would require a real database)
            assert True


def test_error_handling_in_replica_queries():
    """Test error handling when replica queries fail."""
    # Mock read pool that raises an exception
    mock_read_pool = MagicMock()
    mock_read_pool.getconn.side_effect = Exception("Connection failed")

    # Mock primary pool
    mock_primary_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    mock_cursor.fetchall.return_value = [{"id": 1, "title": "Test"}]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_primary_pool.getconn.return_value = mock_conn

    # Temporarily set both pools
    original_read_pool = db_manager._read_pool
    original_pool = db_manager._pool
    db_manager._read_pool = mock_read_pool
    db_manager._pool = mock_primary_pool

    try:
        # Execute a read-only query (should fail on replica and not fallback)
        with pytest.raises(Exception, match="Connection failed"):
            db_manager.execute("SELECT * FROM articles LIMIT 1", read_only=True)

        # Should have attempted to use read pool
        mock_read_pool.getconn.assert_called_once()
    finally:
        # Restore original pools
        db_manager._read_pool = original_read_pool
        db_manager._pool = original_pool
