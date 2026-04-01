"""Tests for database.py — connection wrapper and utility functions."""
import pytest
from unittest.mock import patch, MagicMock


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

        import database
        database._load_env()

    @patch('os.path.exists', return_value=False)
    def test_missing_env_file_no_error(self, mock_exists):
        import database
        # Should not raise when .env doesn't exist
        database._load_env()


class TestDBWrapper:
    """Tests for the DBWrapper connection wrapper."""

    def test_cursor_uses_dict_cursor(self):
        from database import DBWrapper
        from psycopg2.extras import DictCursor
        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.cursor()
        mock_conn.cursor.assert_called_with(cursor_factory=DictCursor)

    def test_close_returns_to_manager(self):
        from database import DBWrapper
        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.close()
        mock_manager.put_conn.assert_called_once_with(mock_conn)

    def test_commit_delegates(self):
        from database import DBWrapper
        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.commit()
        mock_conn.commit.assert_called_once()

    def test_rollback_delegates(self):
        from database import DBWrapper
        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.rollback()
        mock_conn.rollback.assert_called_once()

    def test_context_manager(self):
        from database import DBWrapper
        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        with DBWrapper(mock_manager) as wrapper:
            assert wrapper is not None
        mock_manager.put_conn.assert_called_once_with(mock_conn)


class TestDatabaseManagerExecute:
    """Tests for DatabaseManager.execute method."""

    def test_execute_fetch_returns_dicts(self):
        from database import DatabaseManager
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [{"id": 1}]

        manager = DatabaseManager.__new__(DatabaseManager)
        manager._pool = mock_pool
        result = manager.execute("SELECT 1")
        assert isinstance(result, list)

    def test_execute_no_fetch_commits(self):
        from database import DatabaseManager
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = DatabaseManager.__new__(DatabaseManager)
        manager._pool = mock_pool
        result = manager.execute("INSERT INTO foo VALUES (1)", fetch=False)
        mock_conn.commit.assert_called_once()

    def test_execute_rolls_back_on_error(self):
        from database import DatabaseManager
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = DatabaseManager.__new__(DatabaseManager)
        manager._pool = mock_pool
        with pytest.raises(Exception):
            manager.execute("SELECT boom")
        mock_conn.rollback.assert_called_once()


class TestGetDb:
    def test_get_db_returns_wrapper(self):
        from database import get_db, DBWrapper
        with patch('database.db_manager') as mock_manager:
            mock_manager.get_conn.return_value = MagicMock()
            conn = get_db()
            assert isinstance(conn, DBWrapper)

    def test_search_articles_empty_query(self):
        """search_articles returns [] for empty/too-long queries."""
        from database import DatabaseManager
        manager = DatabaseManager.__new__(DatabaseManager)
        manager._pool = MagicMock()
        assert manager.search_articles("") == []
        assert manager.search_articles("x" * 501) == []
