import json
from unittest.mock import MagicMock, patch

from tasks.utils import reprioritize_maintenance_queue


def _message(task_name: str, *, argsrepr: str = "()", kwargsrepr: str = "{}") -> str:
    return json.dumps(
        {
            "headers": {
                "task": task_name,
                "argsrepr": argsrepr,
                "kwargsrepr": kwargsrepr,
            }
        }
    )


class TestMaintenanceQueueGroom:
    def test_dedupes_periodic_and_metadata_tasks(self):
        messages = (
            [_message("tasks.maintenance.prune_intel_queue_task")] * 5
            + [_message("tasks.intelligence.generate_cluster_metadata_task", kwargsrepr="{'target_clusters': ['abc123']}")] * 3
            + [_message("tasks.intelligence.generate_cluster_metadata_task", kwargsrepr="{'target_clusters': ['def456']}")] * 2
            + [_message("tasks.intelligence.upgrade_fast_synthesis_task", argsrepr="('abc123',)")] * 2
        )
        fake_redis = MagicMock()
        fake_redis.lrange.return_value = messages

        with patch("tasks.utils.redis_client", fake_redis), patch(
            "tasks.utils.get_celery_queue_depth",
            side_effect=[200, 4],
        ):
            result = reprioritize_maintenance_queue()

        assert result["removed"] == 8
        assert result["depth_after"] == 4

    def test_caps_deferrable_tasks_when_queue_stays_congested(self):
        messages = [
            _message("tasks.maintenance.prune_intel_queue_task"),
            *[
                _message(
                    "tasks.intelligence.generate_cluster_metadata_task",
                    kwargsrepr=f"{{'target_clusters': ['cluster-{idx}']}}",
                )
                for idx in range(130)
            ],
        ]
        fake_redis = MagicMock()
        fake_redis.lrange.return_value = messages

        with patch("tasks.utils.redis_client", fake_redis), patch(
            "tasks.utils.get_celery_queue_depth",
            side_effect=[200, 41],
        ):
            result = reprioritize_maintenance_queue()

        assert result["removed"] == 90
        assert result["depth_after"] == 41
