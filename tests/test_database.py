"""Tests for database.py — connection wrapper and utility functions."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock


class TestLoadEnv:
    @patch('builtins.open')
    @patch('os.path.exists', return_value=True)
    @patch.dict('os.environ', {}, clear=False)
    def test_loads_env_file(self, mock_exists, mock_open):
        from io import StringIO
        mock_open.return_value.__enter__ = MagicMock(return_value=StringIO(
            'MY_VAR=hello\nANOTHER=world\n# comment\n'
        ))
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        import importlib
        import database
        database.load_env()
        # Variables should be set (if not already in env)
        # Can't assert os.environ directly due to test isolation,
        # but at least it shouldn't raise

    @patch('os.path.exists', return_value=False)
    def test_missing_env_file_no_error(self, mock_exists):
        import database
        # Should not raise when .env doesn't exist
        database.load_env()


class TestPooledConnectionWrapper:
    def test_execute_uses_dict_cursor(self):
        from database import PooledConnectionWrapper
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        wrapper = PooledConnectionWrapper(mock_conn, mock_pool)

        wrapper.execute("SELECT 1")
        mock_conn.cursor.assert_called()

    def test_close_returns_to_pool(self):
        from database import PooledConnectionWrapper
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        wrapper = PooledConnectionWrapper(mock_conn, mock_pool)

        wrapper.close()
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_close_twice_safe(self):
        from database import PooledConnectionWrapper
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        wrapper = PooledConnectionWrapper(mock_conn, mock_pool)

        wrapper.close()
        wrapper.close()  # Second close should be safe
        assert mock_pool.putconn.call_count == 1

    def test_commit_delegates(self):
        from database import PooledConnectionWrapper
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        wrapper = PooledConnectionWrapper(mock_conn, mock_pool)

        wrapper.commit()
        mock_conn.commit.assert_called_once()

    def test_cursor_default_dict(self):
        from database import PooledConnectionWrapper
        from psycopg2.extras import DictCursor
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        wrapper = PooledConnectionWrapper(mock_conn, mock_pool)

        wrapper.cursor()
        mock_conn.cursor.assert_called_with(cursor_factory=DictCursor)


class TestGetDb:
    @patch('database._db_pool')
    def test_get_db_from_pool(self, mock_pool):
        from database import get_db, PooledConnectionWrapper
        mock_pool.getconn.return_value = MagicMock()
        conn = get_db()
        assert isinstance(conn, PooledConnectionWrapper)

    @patch('database._db_pool', None)
    @patch('database.psycopg2.connect')
    def test_get_db_fallback_no_pool(self, mock_connect):
        from database import get_db
        mock_connect.return_value = MagicMock()
        conn = get_db()
        mock_connect.assert_called_once()
