from unittest.mock import patch

from tasks.maintenance import (
    catch_up_cluster_syntheses_task,
    catch_up_recent_summaries_task,
    ensure_ingestion_freshness_task,
    prioritize_homepage_syntheses_task,
    refresh_fallback_syntheses_task,
    refresh_low_score_syntheses_task,
    refresh_synthesis_quality_task,
    upgrade_stuck_fast_syntheses_task,
)


class TestCatchUpRecentSummaries:
    def test_skips_when_backlog_full(self):
        with patch("tasks.intelligence.intelligence_batches_deferred", return_value=True):
            result = catch_up_recent_summaries_task()
        assert result == {"skipped": True, "reason": "backlog_full"}

    def test_enqueues_recent_unsummarized_articles(self):
        with (
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.utils.get_celery_queue_depth", return_value=100),
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


class TestUpgradeStuckFastSyntheses:
    def test_enqueues_stuck_cluster_upgrades(self):
        with (
            patch(
                "core.synthesis_quality.list_stuck_fast_synthesis_cluster_ids",
                return_value=["cluster-a", "cluster-b"],
            ),
            patch("tasks.maintenance.schedule_task_once", side_effect=[True, False]) as mock_schedule,
        ):
            result = upgrade_stuck_fast_syntheses_task(limit=5)

        assert result == {"enqueued": 1, "stuck_total": 2}
        assert mock_schedule.call_count == 2
        assert mock_schedule.call_args.kwargs["queue"] == "maintenance"


class TestRefreshFallbackSyntheses:
    def test_skips_when_backlog_full(self):
        with patch("tasks.intelligence.intelligence_batches_deferred", return_value=True):
            result = refresh_fallback_syntheses_task()
        assert result == {"skipped": True, "reason": "backlog_full"}

    def test_enqueues_fallback_clusters(self):
        with (
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.maintenance.db") as mock_db,
            patch("tasks.intelligence.synthesize_cluster_task") as mock_task,
        ):
            mock_db.execute.return_value = [
                {"cluster_id": "cluster-a"},
                {"cluster_id": "cluster-b"},
            ]
            result = refresh_fallback_syntheses_task(limit=5)

        assert result == {"enqueued": 2, "candidates": 2}
        assert mock_task.apply_async.call_count == 2


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
    def test_skips_when_backlog_full(self):
        with patch("tasks.intelligence.intelligence_batches_deferred", return_value=True):
            result = catch_up_cluster_syntheses_task()
        assert result == {"skipped": True, "reason": "backlog_full"}


class TestPrioritizeHomepageSyntheses:
    def test_skips_when_backlog_full(self):
        with patch("tasks.intelligence.intelligence_batches_deferred", return_value=True):
            result = prioritize_homepage_syntheses_task()
        assert result == {"skipped": True, "reason": "backlog_full"}

    def test_enqueues_stale_homepage_clusters(self):
        payload = {
            "clusters": [
                {
                    "cluster_id": "home-1",
                    "has_synthesis": False,
                    "articles": [{"id": 1}, {"id": 2}],
                    "synthesis_freshness": {"is_stale": True},
                }
            ]
        }
        with (
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.utils.get_celery_queue_depth", return_value=100),
            patch("tasks.utils.safe_async_run", return_value=payload),
            patch("tasks.intelligence.synthesize_cluster_task") as mock_task,
        ):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result["enqueued"] == 1
        mock_task.apply_async.assert_called_once()

    def test_enqueues_provisional_homepage_clusters(self):
        payload = {
            "clusters": [
                {
                    "cluster_id": "home-2",
                    "has_synthesis": True,
                    "articles": [{"id": 1}, {"id": 2}],
                    "synthesis_freshness": {"is_stale": False},
                    "synthesis_meta": {"needs_upgrade": True},
                }
            ]
        }
        with (
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.utils.get_celery_queue_depth", return_value=100),
            patch("tasks.utils.safe_async_run", return_value=payload),
            patch("tasks.intelligence.synthesize_cluster_task") as mock_task,
        ):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result["enqueued"] == 1
        mock_task.apply_async.assert_called_once()


class TestRefreshLowScoreSyntheses:
    def test_skips_when_backlog_full(self):
        with patch("tasks.intelligence.intelligence_batches_deferred", return_value=True):
            result = refresh_low_score_syntheses_task()
        assert result == {"skipped": True, "reason": "backlog_full"}

    def test_enqueues_low_score_clusters(self):
        with (
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.maintenance.db") as mock_db,
            patch("tasks.intelligence.synthesize_cluster_task") as mock_task,
        ):
            mock_db.execute.return_value = [{"cluster_id": "cluster-a", "lang": "sr", "quality_score": 0.62}]
            result = refresh_low_score_syntheses_task(min_score=0.75, limit=5)

        assert result == {"enqueued": 1}
        mock_task.apply_async.assert_called_once()


class TestBoostHomepageClusterSupply:
    def test_skips_when_backlog_full(self):
        from tasks.maintenance import boost_homepage_cluster_supply_task

        with patch("tasks.intelligence.intelligence_batches_deferred", return_value=True):
            result = boost_homepage_cluster_supply_task()
        assert result == {"skipped": True, "reason": "backlog_full"}

    def test_runs_recluster_and_repair(self):
        from tasks.maintenance import boost_homepage_cluster_supply_task

        with (
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.intelligence.cluster_ops.recluster_recent_articles_task", return_value={"reclustered": 3}) as mock_recluster,
            patch("tasks.intelligence.cluster_ops.repair_split_clusters_task", return_value={"merges": []}) as mock_repair,
            patch("tasks.utils.get_celery_queue_depth", return_value=120),
        ):
            result = boost_homepage_cluster_supply_task()

        assert result["recluster"] == {"reclustered": 3}
        assert result["repair_split"] == {"merges": []}
        mock_recluster.assert_called_once()
        mock_repair.assert_called_once()
