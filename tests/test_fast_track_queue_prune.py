import json
from unittest.mock import MagicMock, patch

from tasks.utils import reprioritize_fast_track_queue


def _message(task_name: str) -> str:
    return json.dumps({"headers": {"task": task_name, "id": f"{task_name}-id"}})


class TestFastTrackQueuePrune:
    def test_skips_when_below_groom_threshold(self):
        with patch("tasks.utils.get_celery_queue_depth", return_value=20):
            result = reprioritize_fast_track_queue()

        assert result["skipped"] is True
        assert result["reason"] == "below_groom_threshold"

    def test_drops_misrouted_synthesis_tasks(self):
        messages = [
            _message("tasks.intelligence.synthesize_cluster_task"),
            _message("tasks.intelligence.synthesize_cluster_task"),
            json.dumps(
                {
                    "headers": {
                        "task": "tasks.intelligence.synthesize_urgent_task",
                        "id": "tasks.intelligence.synthesize_urgent_task-id",
                        "argsrepr": "('cluster-urgent', None)",
                    }
                }
            ),
            _message("tasks.intelligence.auto_summarize_task"),
            _message("tasks.intelligence.auto_summarize_task"),
        ]

        mock_redis = MagicMock()
        mock_redis.lrange.return_value = messages
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with (
            patch("tasks.utils.get_celery_queue_depth", side_effect=[120, 2]),
            patch("tasks.utils.redis_client", mock_redis),
        ):
            result = reprioritize_fast_track_queue()

        assert result["removed"] == 3
        assert result["priority_count"] == 1
        assert result["depth_after"] == 2
        mock_pipe.delete.assert_called_once_with("fast-track")
        mock_pipe.rpush.assert_called_once()
        rebuilt = mock_pipe.rpush.call_args.args[1:]
        assert len(rebuilt) == 2
        assert json.loads(rebuilt[0])["headers"]["task"] == "tasks.intelligence.synthesize_urgent_task"

    def test_deduplicates_urgent_tasks_by_cluster(self):
        def _urgent(cluster_id: str, task_id: str) -> str:
            return json.dumps(
                {
                    "headers": {
                        "task": "tasks.intelligence.synthesize_urgent_task",
                        "id": task_id,
                        "argsrepr": f"('{cluster_id}', None)",
                    }
                }
            )

        messages = [
            _urgent("cluster-a", "urgent-a-1"),
            _urgent("cluster-a", "urgent-a-2"),
            _urgent("cluster-b", "urgent-b"),
            _urgent("cluster-a", "urgent-a-3"),
        ]

        mock_redis = MagicMock()
        mock_redis.lrange.return_value = messages
        mock_pipe = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with (
            patch("tasks.utils.get_celery_queue_depth", side_effect=[200, 2]),
            patch("tasks.utils.redis_client", mock_redis),
        ):
            result = reprioritize_fast_track_queue()

        assert result["removed"] == 2
        assert result["urgent_deduped"] == 2
        assert result["priority_count"] == 2
        rebuilt = mock_pipe.rpush.call_args.args[1:]
        assert len(rebuilt) == 2
