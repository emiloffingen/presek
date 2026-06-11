from unittest.mock import patch

from tasks.maintenance import catch_up_recent_summaries_task, refresh_synthesis_quality_task


class TestCatchUpRecentSummaries:
    def test_skips_when_backlog_high(self):
        with patch("tasks.intelligence.intelligence_secondary_deferred", return_value=True):
            result = catch_up_recent_summaries_task()
        assert result == {"skipped": True, "reason": "backlog_high"}

    def test_enqueues_recent_unsummarized_articles(self):
        with (
            patch("tasks.intelligence.intelligence_secondary_deferred", return_value=False),
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.maintenance.db") as mock_db,
            patch("tasks.intelligence._dispatch_batched") as mock_dispatch,
        ):
            mock_db.execute.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
            result = catch_up_recent_summaries_task(hours=24, limit=50)

        assert result == {"enqueued": 3}
        mock_dispatch.assert_called_once()


class TestRefreshSynthesisQuality:
    def test_writes_snapshot_to_redis(self):
        snapshot = {"status": "ok", "celery_queue_depth": 42}
        with (
            patch("scripts.monitor_synthesis_quality.build_snapshot", return_value=snapshot),
            patch("scripts.monitor_synthesis_quality._write_redis") as mock_write,
        ):
            result = refresh_synthesis_quality_task()

        assert result == snapshot
        mock_write.assert_called_once_with(snapshot)
