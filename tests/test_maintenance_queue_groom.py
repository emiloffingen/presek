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
            + [
                _message(
                    "tasks.intelligence.generate_cluster_metadata_task", kwargsrepr="{'target_clusters': ['abc123']}"
                )
            ]
            * 3
            + [
                _message(
                    "tasks.intelligence.generate_cluster_metadata_task", kwargsrepr="{'target_clusters': ['def456']}"
                )
            ]
            * 2
            + [_message("tasks.intelligence.upgrade_fast_synthesis_task", argsrepr="('abc123',)")] * 2
        )
        fake_redis = MagicMock()
        fake_redis.lrange.return_value = messages

        with (
            patch("tasks.utils.redis_client", fake_redis),
            patch(
                "tasks.utils.get_celery_queue_depth",
                side_effect=[200, 3],
            ),
        ):
            result = reprioritize_maintenance_queue()

        assert result["removed"] == 9
        assert result["depth_after"] == 3

    def test_drops_misrouted_upgrade_tasks(self):
        messages = [
            _message("tasks.intelligence.upgrade_fast_synthesis_task", argsrepr="('abc123',)"),
            _message("tasks.maintenance.prune_fast_track_queue_task"),
            _message("tasks.maintenance.prune_maintenance_queue_task"),
        ]
        fake_redis = MagicMock()
        fake_pipe = MagicMock()
        fake_redis.lrange.return_value = messages
        fake_redis.pipeline.return_value = fake_pipe

        with (
            patch("tasks.utils.redis_client", fake_redis),
            patch(
                "tasks.utils.get_celery_queue_depth",
                side_effect=[200, 2],
            ),
        ):
            result = reprioritize_maintenance_queue()

        assert result["removed"] == 1
        assert result["depth_after"] == 2
        rebuilt = fake_pipe.rpush.call_args.args[1:]
        assert json.loads(rebuilt[0])["headers"]["task"] == "tasks.maintenance.prune_fast_track_queue_task"

    def test_dedupes_repair_single_source_tasks(self):
        messages = [
            _message("tasks.ingestion_task.repair_single_source_task", argsrepr="('source-a',)"),
            _message("tasks.ingestion_task.repair_single_source_task", argsrepr="('source-a',)"),
            _message("tasks.maintenance.prune_crawl_queue_task"),
        ]
        fake_redis = MagicMock()
        fake_pipe = MagicMock()
        fake_redis.lrange.return_value = messages
        fake_redis.pipeline.return_value = fake_pipe

        with (
            patch("tasks.utils.redis_client", fake_redis),
            patch(
                "tasks.utils.get_celery_queue_depth",
                side_effect=[200, 2],
            ),
        ):
            result = reprioritize_maintenance_queue()

        assert result["removed"] == 1
        assert result["depth_after"] == 2

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

        with (
            patch("tasks.utils.redis_client", fake_redis),
            patch(
                "tasks.utils.get_celery_queue_depth",
                side_effect=[200, 41],
            ),
        ):
            result = reprioritize_maintenance_queue()

        assert result["removed"] == 90
        assert result["depth_after"] == 41
