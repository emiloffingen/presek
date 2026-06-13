"""Tests for database.py — connection wrapper and utility functions."""

from unittest.mock import MagicMock, patch

import pytest


def _fresh_database_manager():
    """Return an isolated DatabaseManager without touching the process singleton."""
    from core.database import DatabaseManager

    manager = object.__new__(DatabaseManager)
    manager._pool = None
    manager._read_pool = None
    return manager


class TestDBWrapper:
    """Tests for the DBWrapper connection wrapper."""

    def test_cursor_uses_dict_cursor(self):
        from core.database import DBWrapper

        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.cursor()
        mock_conn.cursor.assert_called_with()

    def test_close_returns_to_manager(self):
        from core.database import DBWrapper

        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.close()
        mock_manager.put_conn.assert_called_once_with(mock_conn)

    def test_commit_delegates(self):
        from core.database import DBWrapper

        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.commit()
        mock_conn.commit.assert_called_once()

    def test_rollback_delegates(self):
        from core.database import DBWrapper

        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        wrapper = DBWrapper(mock_manager)
        wrapper.rollback()
        mock_conn.rollback.assert_called_once()

    def test_context_manager(self):
        from core.database import DBWrapper

        mock_manager = MagicMock()
        mock_conn = MagicMock()
        mock_manager.get_conn.return_value = mock_conn

        with DBWrapper(mock_manager) as wrapper:
            assert wrapper is not None
        mock_manager.put_conn.assert_called_once_with(mock_conn)


class TestDatabaseManagerExecute:
    """Tests for DatabaseManager.execute method."""

    def test_reset_pool_rebuilds_primary_and_read_pools(self):
        from core.database import DatabaseManager

        manager = _fresh_database_manager()
        primary = MagicMock()
        read = MagicMock()
        manager._pool = primary
        manager._read_pool = read

        with patch.object(manager, "_init_pool") as mock_init_primary, patch.object(
            manager, "_init_read_pool"
        ) as mock_init_read:
            manager._reset_pool()

        primary.close.assert_called_once()
        read.close.assert_called_once()
        mock_init_primary.assert_called_once()
        mock_init_read.assert_called_once()

    def test_execute_fetch_returns_dicts(self):
        from core.database import DatabaseManager

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [{"id": 1}]

        manager = _fresh_database_manager()
        manager._pool = mock_pool
        manager._read_pool = None
        result = manager.execute("SELECT 1")
        assert isinstance(result, list)

    def test_execute_no_fetch_commits(self):
        from core.database import DatabaseManager

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = _fresh_database_manager()
        manager._pool = mock_pool
        manager._read_pool = None
        manager.execute("INSERT INTO foo VALUES (1)", fetch=False)
        mock_conn.commit.assert_called_once()

    def test_execute_rolls_back_on_error(self):
        from core.database import DatabaseManager

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager = _fresh_database_manager()
        manager._pool = mock_pool
        manager._read_pool = None
        with pytest.raises(Exception):
            manager.execute("SELECT boom")
        mock_conn.rollback.assert_called_once()

    def test_get_db_size_returns_float(self):
        from core.database import DatabaseManager

        manager = _fresh_database_manager()
        manager.execute_one = MagicMock(return_value={"mb": 128.4})
        assert manager.get_db_size() == 128.4
        manager.execute_one.assert_called_once()

    def test_get_db_size_returns_zero_when_missing(self):
        from core.database import DatabaseManager

        manager = _fresh_database_manager()
        manager.execute_one = MagicMock(return_value=None)
        assert manager.get_db_size() == 0.0


class TestGetDb:
    def test_get_db_returns_wrapper(self):
        from core.database import DBWrapper, get_db

        with patch("core.database.db_manager") as mock_manager:
            mock_manager.get_conn.return_value = MagicMock()
            conn = get_db()
            assert isinstance(conn, DBWrapper)

    def test_search_articles_empty_query(self):
        """search_articles returns [] for empty/too-long queries."""
        from core.database import DatabaseManager

        manager = _fresh_database_manager()
        manager._pool = MagicMock()
        assert manager.search_articles("") == []
        assert manager.search_articles("x" * 501) == []


class TestSchemaMigrations:
    def test_init_schema_calls_alembic_upgrade(self):
        from unittest.mock import patch

        from core.database import DatabaseManager

        manager = _fresh_database_manager()

        with (
            patch("alembic.command.upgrade") as mock_upgrade,
            patch("alembic.config.Config") as mock_config,
            patch("os.path.exists", return_value=True),
        ):

            manager.init_schema()

            assert mock_upgrade.called
            assert mock_upgrade.call_args[0][1] == "head"
            assert mock_config.called
