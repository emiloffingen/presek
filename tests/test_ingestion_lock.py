from unittest.mock import MagicMock, patch

from core.ingestion_lock import (
    INGESTION_LOCK_KEY,
    INGESTION_LOCK_TTL_SECONDS,
    is_ingestion_in_flight,
    release_ingestion_lock,
    renew_ingestion_lock,
    try_acquire_ingestion_lock,
)


class TestIngestionLock:
    def test_acquire_uses_one_hour_ttl(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert try_acquire_ingestion_lock() is True
        mock_redis.set.assert_called_once_with(
            INGESTION_LOCK_KEY,
            "1",
            nx=True,
            ex=INGESTION_LOCK_TTL_SECONDS,
        )

    def test_acquire_returns_none_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.set.side_effect = RuntimeError("redis down")
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert try_acquire_ingestion_lock() is None

    def test_renew_extends_lock_ttl(self):
        mock_redis = MagicMock()
        mock_redis.expire.return_value = 1
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert renew_ingestion_lock() is True
        mock_redis.expire.assert_called_once_with(INGESTION_LOCK_KEY, INGESTION_LOCK_TTL_SECONDS)

    def test_release_deletes_lock(self):
        mock_redis = MagicMock()
        with patch("core.ingestion_lock.redis_client", mock_redis):
            release_ingestion_lock()
        mock_redis.delete.assert_called_once_with(INGESTION_LOCK_KEY)

    def test_in_flight_checks_lock_exists(self):
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert is_ingestion_in_flight() is True
