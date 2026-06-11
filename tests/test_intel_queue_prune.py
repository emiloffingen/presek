import json
from unittest.mock import MagicMock, patch

from tasks.utils import reprioritize_intel_queue


def _message(task_name: str) -> str:
    return json.dumps({"headers": {"task": task_name, "id": f"{task_name}-id"}})


class TestReprioritizeIntelQueue:
    def test_skips_when_below_groom_threshold(self):
        with patch("tasks.utils.get_celery_queue_depth", return_value=50):
            result = reprioritize_intel_queue(defer_threshold=150, groom_threshold=80)
        assert result["skipped"] is True
        assert result["reason"] == "below_groom_threshold"

    def test_grooms_when_above_soft_threshold(self):
        messages = [
            _message("tasks.intelligence.extract_entities_task"),
            _message("tasks.intelligence.summarize_articles_local_batch_task"),
            _message("tasks.intelligence.detect_global_stories_batch_task"),
        ]
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = messages
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with (
            patch("tasks.utils.get_celery_queue_depth", side_effect=[92, 1]),
            patch("tasks.utils.redis_client", mock_redis),
        ):
            result = reprioritize_intel_queue(defer_threshold=150, groom_threshold=80)

        assert result["removed"] == 2
        assert result["priority_count"] == 1
        assert result["depth_after"] == 1

    def test_keeps_summarize_and_drops_secondary_tasks(self):
        messages = [
            _message("tasks.intelligence.extract_entities_task"),
            _message("tasks.intelligence.summarize_articles_batch_task"),
            _message("tasks.intelligence.detect_global_stories_batch_task"),
            _message("tasks.intelligence.summarize_articles_batch_task"),
        ]
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = messages
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with (
            patch("tasks.utils.get_celery_queue_depth", side_effect=[200, 2]),
            patch("tasks.utils.redis_client", mock_redis),
        ):
            result = reprioritize_intel_queue(defer_threshold=150)

        assert result["removed"] == 2
        assert result["priority_count"] == 2
        assert result["depth_after"] == 2
        mock_pipe.delete.assert_called_once_with("intel-heavy")
        mock_pipe.rpush.assert_called_once()
        rebuilt = mock_pipe.rpush.call_args.args[1:]
        assert len(rebuilt) == 2
        assert all("summarize_articles_batch_task" in item for item in rebuilt)

    def test_dry_run_does_not_write(self):
        messages = [_message("tasks.intelligence.backfill_cluster_summaries_task")]
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = messages

        with (
            patch("tasks.utils.get_celery_queue_depth", return_value=200),
            patch("tasks.utils.redis_client", mock_redis),
        ):
            result = reprioritize_intel_queue(defer_threshold=150, dry_run=True)

        assert result["removed"] == 1
        assert result["dry_run"] is True
        mock_redis.pipeline.assert_not_called()
