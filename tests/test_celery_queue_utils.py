from unittest.mock import MagicMock, patch

from tasks.utils import get_celery_queue_depth


class TestCeleryQueueDepth:
    def test_default_returns_max_across_monitored_queues(self):
        class FakeRedis:
            def llen(self, name):
                depths = {
                    "celery": 0,
                    "ingestion": 12,
                    "fast-track": 4,
                    "intel-heavy": 3594,
                    "delivery": 0,
                    "maintenance": 7,
                }
                return depths.get(name, 0)

        with patch("tasks.utils.redis_client", FakeRedis()):
            assert get_celery_queue_depth() == 3594

    def test_named_queue_returns_specific_depth(self):
        fake_redis = MagicMock()
        fake_redis.llen.return_value = 42

        with patch("tasks.utils.redis_client", fake_redis):
            assert get_celery_queue_depth("ingestion") == 42
            fake_redis.llen.assert_called_once_with("ingestion")
