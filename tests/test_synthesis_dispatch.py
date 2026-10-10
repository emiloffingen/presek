from unittest.mock import patch

from tasks.utils import synthesis_dispatch_deferred


class TestSynthesisDispatchDeferred:
    def test_defers_when_synthesis_queue_full(self):
        with patch("tasks.utils.get_celery_queue_depth", side_effect=lambda q=None: 60 if q == "synthesis" else 0):
            assert synthesis_dispatch_deferred() is True

    def test_defers_when_intel_queue_backlogged(self):
        with patch(
            "tasks.utils.get_celery_queue_depth",
            side_effect=lambda q=None: 800 if q == "intel-heavy" else 10,
        ):
            assert synthesis_dispatch_deferred() is True

    def test_allows_dispatch_when_only_maintenance_backlogged(self):
        with (
            patch(
                "tasks.utils.get_celery_queue_depth",
                side_effect=lambda q=None: {
                    "synthesis": 20,
                    "maintenance": 400,
                    "intel-heavy": 120,
                }.get(q, 0),
            ),
            patch("tasks.utils.fast_track_dispatches_deferred", return_value=False),
        ):
            assert synthesis_dispatch_deferred() is False
