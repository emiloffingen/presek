import json
from unittest.mock import patch

from tasks.maintenance import catch_up_deferred_crawls_task, prune_crawl_queue_task
from tasks.utils import (
    crawl_dispatch_cap,
    crawl_dispatches_deferred,
    filter_dead_crawls,
    is_permanent_crawl_error,
    mark_crawl_dead,
    prune_crawl_queue,
)


def _crawl_message(article_id: int, url: str = "https://example.com/a") -> str:
    return json.dumps(
        {
            "headers": {
                "task": "tasks.ingestion_task.crawl_article_task",
                "argsrepr": f"({article_id}, '{url}')",
            }
        }
    )


class TestCrawlDispatchHelpers:
    def test_crawl_dispatches_deferred_when_queue_full(self):
        with patch("tasks.utils.get_celery_queue_depth", return_value=500):
            assert crawl_dispatches_deferred() is True

    def test_crawl_dispatch_cap_when_elevated(self):
        with patch("tasks.utils.get_celery_queue_depth", return_value=200):
            assert crawl_dispatch_cap() == 30

    def test_crawl_dispatch_cap_none_when_healthy(self):
        with patch("tasks.utils.get_celery_queue_depth", return_value=20):
            assert crawl_dispatch_cap() is None


class TestPruneCrawlQueue:
    def test_dedupes_duplicate_article_ids(self):
        messages = [_crawl_message(1), _crawl_message(2), _crawl_message(1)]
        with (
            patch("tasks.utils.redis_client") as mock_redis,
            patch("tasks.utils.get_celery_queue_depth", return_value=2),
        ):
            mock_redis.lrange.return_value = messages
            result = prune_crawl_queue(dry_run=True)

        assert result["removed"] == 1
        assert result["depth_after"] == 2

    def test_dedupes_image_and_invalidation_tasks(self):
        messages = [
            _crawl_message(1),
            json.dumps({"headers": {"task": "tasks.ingestion_task.process_article_image_task", "argsrepr": "(1,)"}}),
            json.dumps({"headers": {"task": "tasks.ingestion_task.process_article_image_task", "argsrepr": "(1,)"}}),
            json.dumps({"headers": {"task": "tasks.ingestion_task.post_crawl_invalidation_task", "argsrepr": "(2,)"}}),
            json.dumps({"headers": {"task": "tasks.ingestion_task.post_crawl_invalidation_task", "argsrepr": "(2,)"}}),
        ]
        with (
            patch("tasks.utils.redis_client") as mock_redis,
            patch("tasks.utils.get_celery_queue_depth", side_effect=[5, 3]),
        ):
            mock_redis.lrange.return_value = messages
            result = prune_crawl_queue(dry_run=True)

        assert result["removed"] == 2
        assert result["depth_after"] == 3

    def test_trims_to_soft_limit_after_dedupe(self):
        messages = [_crawl_message(i) for i in range(200)]
        with (
            patch("tasks.utils.redis_client") as mock_redis,
            patch("tasks.utils.get_celery_queue_depth", return_value=200),
            patch("core.runtime_limits.CRAWL_QUEUE_SOFT_LIMIT", 150),
        ):
            mock_redis.lrange.return_value = messages
            result = prune_crawl_queue(dry_run=True)

        assert result["removed"] == 50
        assert result["depth_after"] == 150


class TestCatchUpDeferredCrawls:
    def test_skips_when_crawl_backlog_high(self):
        with patch("tasks.utils.crawl_dispatches_deferred", return_value=True):
            result = catch_up_deferred_crawls_task()
        assert result == {"skipped": True, "reason": "crawl_backlog_high"}

    def test_enqueues_missing_full_content(self):
        with (
            patch("tasks.utils.crawl_dispatches_deferred", return_value=False),
            patch("tasks.utils.get_celery_queue_depth", return_value=40),
            patch("tasks.maintenance.db") as mock_db,
            patch("tasks.ingestion_task.crawl_article_task") as mock_crawl,
        ):
            mock_db.execute.return_value = [{"id": 10, "link": "https://example.com/10"}]
            result = catch_up_deferred_crawls_task(limit=5)

        assert result["enqueued"] == 1
        mock_crawl.delay.assert_called_once_with(10, "https://example.com/10")


class TestDeadCrawls:
    def test_detects_permanent_http_errors(self):
        assert is_permanent_crawl_error("Client error '404 Not Found' for url 'https://x.mk/a'")
        assert is_permanent_crawl_error("Client error '410 Gone' for url 'https://x.mk/a'")
        assert not is_permanent_crawl_error("Client error '429 Too Many Requests' for url 'https://x.mk/a'")
        assert not is_permanent_crawl_error("Server error '503 Service Unavailable' for url 'https://x.mk/a'")
        assert not is_permanent_crawl_error("")

    def test_mark_sets_ttl_longer_than_catch_up_window(self):
        with patch("tasks.utils.redis_client") as mock_redis:
            mark_crawl_dead(7)
        key, value = mock_redis.set.call_args.args
        assert key == "crawl:dead:7"
        assert mock_redis.set.call_args.kwargs["ex"] > 72 * 3600

    def test_filter_drops_marked_rows(self):
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        with patch("tasks.utils.redis_client") as mock_redis:
            mock_redis.mget.return_value = [None, b"1", None]
            assert filter_dead_crawls(rows) == [{"id": 1}, {"id": 3}]

    def test_filter_fails_open_when_redis_down(self):
        rows = [{"id": 1}, {"id": 2}]
        with patch("tasks.utils.redis_client") as mock_redis:
            mock_redis.mget.side_effect = ConnectionError("down")
            assert filter_dead_crawls(rows) == rows

    def test_catch_up_skips_dead_articles(self):
        with (
            patch("tasks.utils.crawl_dispatches_deferred", return_value=False),
            patch("tasks.utils.get_celery_queue_depth", return_value=40),
            patch("tasks.utils.redis_client") as mock_redis,
            patch("tasks.maintenance.db") as mock_db,
            patch("tasks.ingestion_task.crawl_article_task") as mock_crawl,
        ):
            mock_redis.mget.return_value = [b"1", None]
            mock_db.execute.return_value = [
                {"id": 10, "link": "https://example.com/10"},
                {"id": 11, "link": "https://example.com/11"},
            ]
            result = catch_up_deferred_crawls_task(limit=5)

        assert result["enqueued"] == 1
        mock_crawl.delay.assert_called_once_with(11, "https://example.com/11")


class TestPruneCrawlQueueTask:
    def test_task_wraps_helper(self):
        with patch(
            "tasks.maintenance.prune_crawl_queue", return_value={"removed": 2, "depth_before": 5, "depth_after": 3}
        ) as mock_prune:
            result = prune_crawl_queue_task()
        assert result == {"removed": 2, "depth_before": 5, "depth_after": 3}
        mock_prune.assert_called_once_with(dry_run=False)
