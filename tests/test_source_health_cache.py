"""get_source_health_map is called once per scored article; it must not hit Redis each time."""

from unittest.mock import MagicMock, patch

from utils import ranking


def _reset():
    ranking._SOURCE_STATUS_CACHE.update({"time": 0.0, "data": {}})


def test_empty_source_health_hash_is_cached_not_refetched_per_call():
    """The Shield's Redis has no presek:source_statuses hash (ingestion runs on the phone);
    every scored article used to trigger a synchronous HGETALL (~15,000 per listing request),
    which froze the event loop for 10-20 s."""
    _reset()
    fake_redis = MagicMock()
    fake_redis.hgetall.return_value = {}
    with patch.object(ranking, "redis_client", fake_redis):
        for _ in range(500):
            assert ranking.get_source_health_map() == {}
    assert fake_redis.hgetall.call_count == 1


def test_non_empty_source_health_hash_is_cached():
    _reset()
    fake_redis = MagicMock()
    fake_redis.hgetall.return_value = {"N1 Info": '{"quality_score": 0.9}'}
    with patch.object(ranking, "redis_client", fake_redis):
        for _ in range(100):
            assert ranking.get_source_health_map() == {"N1 Info": {"quality_score": 0.9}}
    assert fake_redis.hgetall.call_count == 1


def test_source_health_failure_is_not_retried_on_every_call():
    _reset()
    fake_redis = MagicMock()
    fake_redis.hgetall.side_effect = RuntimeError("redis down")
    with patch.object(ranking, "redis_client", fake_redis):
        for _ in range(200):
            assert ranking.get_source_health_map() == {}
    assert fake_redis.hgetall.call_count == 1
