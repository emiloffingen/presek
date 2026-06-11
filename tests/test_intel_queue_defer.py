from unittest.mock import patch

from tasks.intelligence import (
    intelligence_batches_deferred,
    intelligence_secondary_deferred,
    intelligence_soft_deferred,
)


class TestIntelQueueDefer:
    def test_soft_deferred_at_80(self):
        with patch("tasks.intelligence.get_celery_queue_depth", return_value=80):
            assert intelligence_soft_deferred() is True

    def test_soft_not_deferred_below_threshold(self):
        with patch("tasks.intelligence.get_celery_queue_depth", return_value=79):
            assert intelligence_soft_deferred() is False

    def test_secondary_deferred_at_150(self):
        with patch("tasks.intelligence.get_celery_queue_depth", return_value=150):
            assert intelligence_secondary_deferred() is True

    def test_secondary_not_deferred_below_threshold(self):
        with patch("tasks.intelligence.get_celery_queue_depth", return_value=149):
            assert intelligence_secondary_deferred() is False

    def test_full_deferred_at_800(self):
        with patch("tasks.intelligence.get_celery_queue_depth", return_value=800):
            assert intelligence_batches_deferred() is True

    def test_summarize_allowed_between_thresholds(self):
        with patch("tasks.intelligence.get_celery_queue_depth", return_value=400):
            assert intelligence_secondary_deferred() is True
            assert intelligence_batches_deferred() is False
