from unittest.mock import patch

from tasks.maintenance import (
    catch_up_cluster_syntheses_task,
    catch_up_recent_summaries_task,
    ensure_ingestion_freshness_task,
    refresh_low_score_syntheses_task,
    refresh_synthesis_quality_task,
)


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
            patch("tasks.intelligence.summarize_articles_local_batch_task") as mock_task,
        ):
            mock_db.execute.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
            result = catch_up_recent_summaries_task(hours=24, limit=50)

        assert result == {"enqueued": 3}
        mock_dispatch.assert_called_once_with(mock_task, [1, 2, 3])


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


class TestEnsureIngestionFreshness:
    def test_triggers_ingestion_when_stale(self):
        with (
            patch("core.health.load_last_refresh_time", return_value="2026-06-13T00:00:00+00:00"),
            patch("core.health._freshness_payload", return_value={"age_minutes": 300}),
            patch("core.ingestion_lock.is_ingestion_in_flight", return_value=False),
            patch("tasks.maintenance.prune_ingestion_queue"),
            patch("tasks.ingestion_task.run_ingestion") as mock_ingest,
        ):
            result = ensure_ingestion_freshness_task(max_age_minutes=120)

        assert result["triggered"] is True
        mock_ingest.apply_async.assert_called_once_with(expires=540)

    def test_skips_when_cycle_already_in_flight(self):
        with (
            patch("core.health.load_last_refresh_time", return_value="2026-06-13T00:00:00+00:00"),
            patch("core.health._freshness_payload", return_value={"age_minutes": 300}),
            patch("core.ingestion_lock.is_ingestion_in_flight", return_value=True),
            patch("tasks.ingestion_task.run_ingestion") as mock_ingest,
        ):
            result = ensure_ingestion_freshness_task(max_age_minutes=120)

        assert result == {"skipped": True, "reason": "in_flight", "age_minutes": 300}
        mock_ingest.delay.assert_not_called()


class TestCatchUpClusterSyntheses:
    def test_skips_when_backlog_high(self):
        with patch("tasks.intelligence.intelligence_soft_deferred", return_value=True):
            result = catch_up_cluster_syntheses_task()
        assert result == {"skipped": True, "reason": "backlog_high"}


class TestRefreshLowScoreSyntheses:
    def test_skips_when_backlog_high(self):
        with patch("tasks.intelligence.intelligence_soft_deferred", return_value=True):
            result = refresh_low_score_syntheses_task()
        assert result == {"skipped": True, "reason": "backlog_high"}
