"""Test database read replica functionality."""

from unittest.mock import MagicMock, patch

import pytest

from core.database import db_manager


def test_read_replica_configuration():
    """Test read replica configuration."""
    # Test that config variables exist
    assert hasattr(db_manager, "_read_pool")


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
    import importlib
    import core.database

    # Mock ConnectionPool so it doesn't connect to replica
    with patch("psycopg_pool.ConnectionPool") as mock_conn_pool:
        with patch("core.config.DATABASE_READ_REPLICA_URL", "postgresql://user:pass@replica:5432/db"):
            with patch("core.config.USE_READ_REPLICA", True):
                importlib.reload(core.database)
                
                # Check that ConnectionPool was called with the replica URL
                mock_conn_pool.assert_any_call(
                    conninfo="postgresql://user:pass@replica:5432/db",
                    min_size=core.database.DB_POOL_MINCONN,
                    max_size=core.database.DB_POOL_MAXCONN,
                    open=True,
                    kwargs={
                        "row_factory": core.database.dict_row,
                        "connect_timeout": 5,
                        "options": core.database.DB_SESSION_OPTIONS,
                    },
                )

    # Crucial: Reload core.database once again in a clean environment (no patches)
    # to restore the original db_manager and clean up any mock states
    importlib.reload(core.database)


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


@pytest.mark.asyncio
async def test_async_read_only_query_routing():
    """Test that async read-only queries are routed to the replica pool in AsyncDatabaseManager."""
    from core.database import async_db
    
    # Mock pools for AsyncDatabaseManager
    mock_read_pool = MagicMock()
    mock_primary_pool = MagicMock()
    
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    # Set up mock cursor for async context managers
    async def mock_execute(sql, params=None):
        return None
    async def mock_fetchall():
        return [{"id": 1, "title": "Async Test"}]
        
    async def mock_commit():
        return None
        
    mock_cursor.execute = mock_execute
    mock_cursor.fetchall = mock_fetchall
    mock_conn.commit = mock_commit
    
    # Async connection context managers
    class AsyncConnCM:
        async def __aenter__(self):
            return mock_conn
        async def __aexit__(self, exc_type, exc, tb):
            pass
            
    class AsyncCursorCM:
        async def __aenter__(self):
            return mock_cursor
        async def __aexit__(self, exc_type, exc, tb):
            pass
            
    mock_conn.cursor.return_value = AsyncCursorCM()
    mock_read_pool.connection.return_value = AsyncConnCM()
    mock_primary_pool.connection.return_value = AsyncConnCM()
    
    # Temporarily override AsyncDatabaseManager pools
    original_read_pool = async_db._read_pool
    original_pool = async_db._pool
    
    async_db._read_pool = mock_read_pool
    async_db._pool = mock_primary_pool
    
    try:
        # 1. Execute an explicit read-only query
        results = await async_db.execute("SELECT * FROM articles LIMIT 1", read_only=True)
        assert results == [{"id": 1, "title": "Async Test"}]
        mock_read_pool.connection.assert_called_once()
        mock_primary_pool.connection.assert_not_called()
        
        # Reset mocks
        mock_read_pool.reset_mock()
        mock_primary_pool.reset_mock()
        
        # 2. Execute an auto-detected read-only SELECT query
        results = await async_db.execute("SELECT * FROM articles LIMIT 1")
        assert results == [{"id": 1, "title": "Async Test"}]
        mock_read_pool.connection.assert_called_once()
        mock_primary_pool.connection.assert_not_called()
        
        # Reset mocks
        mock_read_pool.reset_mock()
        mock_primary_pool.reset_mock()
        
        # 3. Execute a write query (e.g. INSERT) which should route to primary
        await async_db.execute("INSERT INTO articles (title) VALUES ('New')", fetch=False)
        mock_read_pool.connection.assert_not_called()
        mock_primary_pool.connection.assert_called_once()
    finally:
        async_db._read_pool = original_read_pool
        async_db._pool = original_pool

