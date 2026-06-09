from core.health import get_operational_status


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
