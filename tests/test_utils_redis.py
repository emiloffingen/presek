"""Tests for Redis-backed utilities: caching and rate limiting."""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_env_for_rate_limit_tests(monkeypatch):
    monkeypatch.setenv("ENV", "test")


class TestCachedResponse:
    @patch("utils.cache.redis_client")
    def test_cache_hit(self, mock_redis):
        from utils import cached_response

        mock_redis.get.return_value = json.dumps({"data": "cached"})
        result = cached_response("test-key", ttl=60)
        assert result == {"data": "cached"}

    @patch("utils.cache.redis_client")
    def test_cache_miss(self, mock_redis):
        from utils import cached_response

        mock_redis.get.return_value = None
        result = cached_response("test-key", ttl=60)
        assert result is None

    @patch("utils.cache.redis_client")
    def test_cache_redis_error(self, mock_redis):
        from utils import cached_response

        mock_redis.get.side_effect = Exception("Connection refused")
        result = cached_response("test-key")
        assert result is None


class TestSetCache:
    @patch("utils.cache.redis_client")
    def test_set_cache_stores_json(self, mock_redis):
        from utils import set_cache

        set_cache("key", {"foo": "bar"}, ttl=120)
        mock_redis.setex.assert_called_once_with("key", 120, json.dumps({"foo": "bar"}))

    @patch("utils.cache.redis_client")
    def test_set_cache_redis_error(self, mock_redis):
        from utils import set_cache

        mock_redis.setex.side_effect = Exception("Connection refused")
        # Should not raise
        set_cache("key", {"foo": "bar"})


class TestCheckRateLimit:
    @patch("utils.cache.redis_client")
    def test_under_limit(self, mock_redis):
        from utils import check_rate_limit

        pipe = MagicMock()
        pipe.execute.return_value = [0, 5, 1, True]  # 5 requests in window
        mock_redis.pipeline.return_value = pipe
        assert check_rate_limit("1.2.3.4") is True

    @patch("utils.cache.redis_client")
    def test_over_limit(self, mock_redis):
        from utils import check_rate_limit

        pipe = MagicMock()
        pipe.execute.return_value = [0, 60, 1, True]  # 60 requests = at limit
        mock_redis.pipeline.return_value = pipe
        assert check_rate_limit("1.2.3.4") is False

    @patch("utils.cache.redis_client")
    def test_redis_failure_allows_request_in_non_production(self, mock_redis, monkeypatch):
        """If Redis is down outside production, rate limiter fails open to keep the site up."""
        from utils import check_rate_limit

        monkeypatch.setenv("ENV", "test")
        mock_redis.pipeline.side_effect = Exception("Connection refused")
        assert check_rate_limit("1.2.3.4") is True

    @patch("utils.cache.redis_client")
    def test_redis_failure_blocks_request_in_production(self, mock_redis, monkeypatch):
        from utils import check_rate_limit

        monkeypatch.setenv("ENV", "production")
        mock_redis.pipeline.side_effect = Exception("Connection refused")
        assert check_rate_limit("1.2.3.4") is False

    @patch("utils.cache.redis_client")
    def test_ai_path_uses_daily_limit(self, mock_redis):
        from utils import check_rate_limit

        pipe = MagicMock()
        pipe.execute.return_value = [0, 0, 1, True]
        mock_redis.pipeline.return_value = pipe
        mock_redis.incr.return_value = 101
        assert check_rate_limit("1.2.3.4", path="/api/intelligence/cluster/abc123/research") is False

    @patch("utils.cache.redis_client")
    def test_ai_path_uses_tighter_window_limit(self, mock_redis):
        from utils import check_rate_limit

        pipe = MagicMock()
        pipe.execute.return_value = [0, 12, 1, True]
        mock_redis.pipeline.return_value = pipe
        mock_redis.incr.return_value = 1
        assert check_rate_limit("1.2.3.4", path="/api/intelligence/cluster/abc123/analyst") is False
