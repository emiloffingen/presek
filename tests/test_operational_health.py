from unittest.mock import patch

from core.health import MONITORED_CELERY_QUEUES, _probe_celery_queue, get_operational_status


class TestOperationalHealth:
    def test_healthy_when_core_services_ok(self):
        assert (
            get_operational_status(
                True,
                True,
                {"status": "ok"},
                {"celery_depth": 0, "degraded": False},
            )
            == "healthy"
        )

    def test_busy_when_queue_warn_threshold_hit(self):
        assert (
            get_operational_status(
                True,
                True,
                {"status": "ok"},
                {"celery_depth": 150, "degraded": True},
            )
            == "busy"
        )

    def test_degraded_on_critical_queue(self):
        assert (
            get_operational_status(
                True,
                True,
                {"status": "ok"},
                {"celery_depth": 600, "degraded": True},
            )
            == "degraded"
        )

    def test_degraded_on_critical_synthesis(self):
        assert (
            get_operational_status(
                True,
                True,
                {"status": "critical"},
                {"celery_depth": 0, "degraded": False},
            )
            == "degraded"
        )

    def test_busy_when_intel_heavy_queue_backlogged(self):
        assert (
            get_operational_status(
                True,
                True,
                {"status": "ok"},
                {"celery_depth": 250, "degraded": True},
            )
            == "busy"
        )


class TestCeleryQueueProbe:
    def test_probe_tracks_all_monitored_queues(self):
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

        with patch("core.health._get_redis", return_value=FakeRedis()):
            snapshot = _probe_celery_queue()

        assert snapshot["celery_depth"] == 3594
        assert snapshot["total_depth"] == 3617
        assert snapshot["degraded"] is True
        assert set(snapshot["queues"]) == set(MONITORED_CELERY_QUEUES)
        assert snapshot["queues"]["intel-heavy"]["depth"] == 3594
