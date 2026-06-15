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
    def test_acquire_uses_owner_token_and_one_hour_ttl(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert try_acquire_ingestion_lock() is True
        args, kwargs = mock_redis.set.call_args
        assert args[0] == INGESTION_LOCK_KEY
        assert len(args[1]) == 32
        assert kwargs == {"nx": True, "ex": INGESTION_LOCK_TTL_SECONDS}

    def test_acquire_returns_none_on_redis_error(self):
        mock_redis = MagicMock()
        mock_redis.set.side_effect = RuntimeError("redis down")
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert try_acquire_ingestion_lock() is None

    def test_renew_extends_lock_only_for_owner(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_redis.eval.return_value = 1
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert try_acquire_ingestion_lock() is True
            assert renew_ingestion_lock() is True
            release_ingestion_lock()
        mock_redis.eval.assert_any_call(
            mock_redis.eval.call_args_list[0].args[0],
            1,
            INGESTION_LOCK_KEY,
            mock_redis.set.call_args.args[1],
            INGESTION_LOCK_TTL_SECONDS,
        )

    def test_renew_without_owner_returns_false(self):
        mock_redis = MagicMock()
        with patch("core.ingestion_lock.redis_client", mock_redis):
            release_ingestion_lock()
            assert renew_ingestion_lock() is False
        mock_redis.eval.assert_not_called()

    def test_release_deletes_lock_only_for_owner(self):
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_redis.eval.return_value = 1
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert try_acquire_ingestion_lock() is True
            release_ingestion_lock()
        assert mock_redis.eval.call_count == 1
        assert mock_redis.eval.call_args.args[2] == INGESTION_LOCK_KEY

    def test_in_flight_checks_lock_exists(self):
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        with patch("core.ingestion_lock.redis_client", mock_redis):
            assert is_ingestion_in_flight() is True
