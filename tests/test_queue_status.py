from unittest.mock import patch

from core.queue_status import (
    get_all_queue_depths,
    get_intel_backlog_status,
    queue_status_payload,
    reader_pipeline_status,
)
from core.runtime_limits import (
    CELERY_QUEUE_WARN_DEPTH,
    INTEL_QUEUE_FULL_DEFER_LIMIT,
    INTEL_QUEUE_SECONDARY_DEFER_LIMIT,
    INTEL_QUEUE_SOFT_DEFER_LIMIT,
)


class TestQueueStatus:
    def test_intel_backlog_status_thresholds(self):
        assert get_intel_backlog_status(0) == "ok"
        assert get_intel_backlog_status(INTEL_QUEUE_SOFT_DEFER_LIMIT) == "elevated"
        assert get_intel_backlog_status(INTEL_QUEUE_SECONDARY_DEFER_LIMIT) == "busy"
        assert get_intel_backlog_status(INTEL_QUEUE_FULL_DEFER_LIMIT) == "backlogged"

    def test_get_all_queue_depths_uses_monitored_queues(self):
        with patch("core.queue_status.redis_client.llen", def side_effect(name):
    return {"intel-heavy": 12}.get(name, 0)):
            depths = get_all_queue_depths()
        assert depths["intel-heavy"] == 12
        assert "ingestion" in depths

    def test_queue_status_payload_shape(self):
        with patch("core.queue_status.redis_client.llen", return_value=90):
            payload = queue_status_payload()
        assert payload["intel_heavy_depth"] == 90
        assert payload["intel_status"] == "elevated"
        assert payload["thresholds"]["soft"] == INTEL_QUEUE_SOFT_DEFER_LIMIT
        assert "depths" in payload

    def test_reader_pipeline_status_marks_busy_at_warn_threshold(self):
        with patch("core.queue_status.redis_client.llen", return_value=CELERY_QUEUE_WARN_DEPTH):
            payload = reader_pipeline_status()
        assert payload["busy"] is True
        assert payload["intel_heavy_depth"] == CELERY_QUEUE_WARN_DEPTH

    def test_reader_pipeline_status_ignores_maintenance_backlog(self):
        def fake_llen(name):
            depths = {
                "maintenance": 400,
                "synthesis": 20,
                "intel-heavy": 30,
            }
            return depths.get(name, 0)

        with patch("core.queue_status.redis_client.llen", side_effect=fake_llen):
            payload = reader_pipeline_status()

        assert payload["total_queue_depth"] == 50
        assert payload["pipeline_status"] == "ok"
        assert payload["busy"] is False
