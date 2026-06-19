from unittest.mock import patch

from tasks.maintenance import (
    catch_up_cluster_syntheses_task,
    catch_up_recent_summaries_task,
    ensure_ingestion_freshness_task,
    filter_cluster_ids_for_synthesis,
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
            patch("tasks.maintenance._homepage_synthesis_only", return_value=False),
            patch("tasks.utils.pipeline_backpressure_active", return_value=False),
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

    def test_limits_catch_up_to_homepage_clusters(self):
        with (
            patch("tasks.maintenance._homepage_synthesis_only", return_value=True),
            patch("tasks.maintenance._collect_homepage_layout_cluster_ids", return_value=["home-1"]),
            patch("tasks.utils.pipeline_backpressure_active", return_value=False),
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.utils.get_celery_queue_depth", return_value=100),
            patch("tasks.maintenance.db") as mock_db,
            patch("tasks.intelligence._dispatch_batched") as mock_dispatch,
            patch("tasks.intelligence.summarize_articles_local_batch_task") as mock_task,
        ):
            mock_db.execute.return_value = [{"id": 9}]
            result = catch_up_recent_summaries_task(hours=24, limit=50)

        assert result == {"enqueued": 1}
        mock_dispatch.assert_called_once_with(mock_task, [9])
        sql = mock_db.execute.call_args.args[0]
        assert "cluster_id = ANY" in sql


class TestFilterClusterIdsForSynthesis:
    def test_keeps_only_homepage_clusters_when_enabled(self):
        with (
            patch("tasks.maintenance._homepage_synthesis_only", return_value=True),
            patch("tasks.maintenance._collect_homepage_layout_cluster_ids", return_value=["home-1", "home-2"]),
        ):
            result = filter_cluster_ids_for_synthesis(["home-1", "feed-9", "home-2", "feed-3"])
        assert result == ["home-1", "home-2"]


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
            patch("tasks.maintenance._homepage_synthesis_only", return_value=False),
            patch("tasks.utils.maintenance_dispatches_deferred", return_value=False),
            patch("core.synthesis_quality.prune_stale_fast_synthesis_pending", return_value=0),
            patch(
                "core.synthesis_quality.list_stuck_fast_synthesis_cluster_ids",
                return_value=["cluster-a", "cluster-b"],
            ),
            patch("tasks.maintenance.schedule_task_once", side_effect=[True, False]) as mock_schedule,
        ):
            result = upgrade_stuck_fast_syntheses_task(limit=5)

        assert result == {"enqueued": 1, "stuck_total": 2, "cleared_pending": 0}
        assert mock_schedule.call_count == 2
        assert mock_schedule.call_args.kwargs["queue"] == "synthesis"


class TestRefreshFallbackSyntheses:
    def test_skips_when_backlog_full(self):
        with patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=True):
            result = refresh_fallback_syntheses_task()
        assert result == {"skipped": True, "reason": "synthesis_backlog"}

    def test_enqueues_fallback_clusters(self):
        with (
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=False),
            patch("tasks.maintenance._collect_homepage_cluster_ids", return_value=["cluster-a"]),
            patch("tasks.maintenance.db") as mock_db,
            patch("tasks.intelligence.synthesize_cluster_task") as mock_task,
            patch("tasks.maintenance._effective_synthesis_refresh_hourly_cap", return_value=120),
        ):
            mock_db.execute.return_value = [
                {"cluster_id": "cluster-a", "latest_at": "2026-06-15"},
                {"cluster_id": "cluster-b", "latest_at": "2026-06-14"},
            ]
            result = refresh_fallback_syntheses_task(limit=5)

        assert result["enqueued"] == 2
        assert result["homepage_enqueued"] == 1
        assert mock_task.apply_async.call_count == 2
        first_call = mock_task.apply_async.call_args_list[0]
        assert first_call.args[0] == ("cluster-a", None)
        assert first_call.kwargs["queue"] == "synthesis"


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
            patch("core.ingestion_lock.break_stale_ingestion_lock", return_value=False),
            patch("tasks.ingestion_task.run_ingestion") as mock_ingest,
        ):
            result = ensure_ingestion_freshness_task(max_age_minutes=120)

        assert result == {"skipped": True, "reason": "in_flight", "age_minutes": 300}
        mock_ingest.delay.assert_not_called()

    def test_breaks_stale_lock_before_triggering_ingestion(self):
        with (
            patch("core.health.load_last_refresh_time", return_value="2026-06-13T00:00:00+00:00"),
            patch("core.health._freshness_payload", return_value={"age_minutes": 300}),
            patch("core.ingestion_lock.is_ingestion_in_flight", return_value=True),
            patch("core.ingestion_lock.break_stale_ingestion_lock", return_value=True),
            patch("tasks.maintenance.prune_ingestion_queue"),
            patch("tasks.ingestion_task.run_ingestion") as mock_ingest,
        ):
            result = ensure_ingestion_freshness_task(max_age_minutes=120)

        assert result["triggered"] is True
        mock_ingest.apply_async.assert_called_once_with(expires=540)


class TestCatchUpClusterSyntheses:
    def test_skips_when_backlog_full(self):
        with (
            patch("tasks.maintenance._homepage_synthesis_only", return_value=False),
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=True),
        ):
            result = catch_up_cluster_syntheses_task()
        assert result == {"skipped": True, "reason": "synthesis_backlog"}

    def test_skips_in_homepage_only_mode(self):
        with patch("tasks.maintenance._homepage_synthesis_only", return_value=True):
            result = catch_up_cluster_syntheses_task()
        assert result == {"skipped": True, "reason": "homepage_only"}


class TestPrioritizeHomepageSyntheses:
    def test_collects_hero_targets_before_other_sections(self):
        sr_payload = {
            "status": "success",
            "lead": {"cluster_id": "lead-sr", "has_synthesis": False, "articles": [{"id": 1}, {"id": 2}]},
            "supporting": [],
            "developing": [
                {"cluster_id": "dev-sr", "has_synthesis": False, "articles": [{"id": 1}, {"id": 2}]},
            ],
        }
        mk_payload = {
            "status": "success",
            "lead": {"cluster_id": "lead-mk", "has_synthesis": False, "articles": [{"id": 1}, {"id": 2}]},
            "supporting": [],
            "developing": [],
        }

        def fake_fetch(lang):
            return sr_payload if lang == "sr" else mk_payload

        with patch("tasks.maintenance._fetch_homepage_payload", side_effect=fake_fetch):
            from tasks.maintenance import _collect_homepage_synthesis_targets

            result = _collect_homepage_synthesis_targets()

        assert result[:2] == ["lead-sr", "lead-mk"]
        assert "dev-sr" in result

    def test_uses_fast_track_when_synthesis_backlogged(self):
        payload = {
            "clusters": [
                {
                    "cluster_id": "home-urgent",
                    "has_synthesis": False,
                    "articles": [{"id": 1}],
                    "synthesis_freshness": {"is_stale": True, "reasons": ["missing_synthesis"]},
                }
            ]
        }
        with (
            patch("tasks.maintenance._homepage_synthesis_only", return_value=False),
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=True),
            patch("tasks.maintenance._synthesis_queue_depth", return_value=55),
            patch("tasks.maintenance._collect_homepage_synthesis_targets", return_value=["home-urgent"]),
            patch("tasks.maintenance._collect_homepage_hero_cluster_ids", return_value=set()),
            patch("tasks.utils.fast_track_dispatches_deferred", return_value=False),
            patch("tasks.utils.maintenance_dispatches_deferred", return_value=False),
            patch("tasks.utils.safe_async_run", return_value=payload),
            patch("tasks.intelligence.synthesis.synthesize_urgent_task") as mock_urgent,
        ):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result["enqueued"] == 1
        assert result["fast_track"] is True
        mock_urgent.apply_async.assert_called_once()
        assert mock_urgent.apply_async.call_args.kwargs["queue"] == "fast-track"

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
            patch("tasks.maintenance._homepage_synthesis_only", return_value=False),
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=False),
            patch("tasks.maintenance._synthesis_queue_depth", return_value=5),
            patch("tasks.maintenance._collect_homepage_synthesis_targets", return_value=["home-1"]),
            patch("tasks.maintenance._collect_homepage_hero_cluster_ids", return_value=set()),
            patch("tasks.utils.fast_track_dispatches_deferred", return_value=False),
            patch("tasks.utils.maintenance_dispatches_deferred", return_value=False),
            patch("tasks.utils.safe_async_run", return_value=payload),
            patch("tasks.intelligence.synthesis.synthesize_cluster_task") as mock_task,
        ):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result["enqueued"] == 1
        mock_task.apply_async.assert_called_once()
        assert mock_task.apply_async.call_args.kwargs["queue"] == "synthesis"

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
            patch("tasks.maintenance._homepage_synthesis_only", return_value=False),
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=False),
            patch("tasks.maintenance._synthesis_queue_depth", return_value=5),
            patch("tasks.maintenance._collect_homepage_synthesis_targets", return_value=["home-2"]),
            patch("tasks.maintenance._collect_homepage_hero_cluster_ids", return_value=set()),
            patch("tasks.utils.fast_track_dispatches_deferred", return_value=False),
            patch("tasks.utils.maintenance_dispatches_deferred", return_value=False),
            patch("tasks.utils.safe_async_run", return_value=payload),
            patch("tasks.intelligence.synthesis.synthesize_cluster_task") as mock_task,
        ):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result["enqueued"] == 1
        mock_task.apply_async.assert_called_once()

    def test_prioritizes_home_layout_lead_before_feed(self):
        home_cluster = {
            "cluster_id": "lead-home",
            "has_synthesis": False,
            "articles": [{"id": 1}],
            "synthesis_freshness": {"is_stale": True, "reasons": ["missing_synthesis"]},
        }
        with (
            patch("tasks.maintenance._homepage_synthesis_only", return_value=True),
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=False),
            patch("tasks.maintenance._synthesis_queue_depth", return_value=5),
            patch("tasks.maintenance._collect_homepage_synthesis_targets", return_value=["lead-home"]),
            patch("tasks.maintenance._collect_homepage_hero_cluster_ids", return_value={"lead-home"}),
            patch("tasks.utils.fast_track_dispatches_deferred", return_value=False),
            patch("tasks.utils.maintenance_dispatches_deferred", return_value=False),
            patch("tasks.intelligence.synthesis.synthesize_urgent_task") as mock_urgent,
        ):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result["enqueued"] == 1
        mock_urgent.apply_async.assert_called_once_with(
            ("lead-home", None),
            countdown=0,
            queue="fast-track",
        )

    def test_skips_when_fast_track_and_synthesis_are_congested(self):
        with (
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=True),
            patch("tasks.maintenance._synthesis_queue_depth", return_value=80),
            patch("tasks.utils.fast_track_dispatches_deferred", return_value=True),
            patch("tasks.utils.maintenance_dispatches_deferred", return_value=False),
        ):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result == {
            "skipped": True,
            "reason": "synthesis_and_fast_track_backlog",
            "synthesis_depth": 80,
        }

    def test_skips_when_maintenance_queue_is_congested(self):
        with patch("tasks.utils.maintenance_dispatches_deferred", return_value=True):
            result = prioritize_homepage_syntheses_task(limit=5)

        assert result == {"skipped": True, "reason": "maintenance_backlog"}


class TestRefreshLowScoreSyntheses:
    def test_skips_when_backlog_full(self):
        with patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=True):
            result = refresh_low_score_syntheses_task()
        assert result == {"skipped": True, "reason": "synthesis_backlog"}

    def test_enqueues_low_score_clusters(self):
        with (
            patch("tasks.maintenance._homepage_synthesis_only", return_value=False),
            patch("tasks.maintenance._synthesis_dispatch_deferred", return_value=False),
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

        with patch("tasks.utils.pipeline_backpressure_active", return_value=True):
            result = boost_homepage_cluster_supply_task()
        assert result == {"skipped": True, "reason": "backlog_full"}

    def test_dispatches_recluster_and_repair(self):
        from tasks.maintenance import boost_homepage_cluster_supply_task

        with (
            patch("tasks.utils.pipeline_backpressure_active", return_value=False),
            patch("tasks.intelligence.intelligence_batches_deferred", return_value=False),
            patch("tasks.utils.acquire_task_lock", return_value=True),
            patch("tasks.intelligence.cluster_ops.recluster_recent_articles_task") as mock_recluster,
            patch("tasks.intelligence.cluster_ops.repair_split_clusters_task") as mock_repair,
            patch("tasks.utils.get_celery_queue_depth", return_value=120),
        ):
            result = boost_homepage_cluster_supply_task()

        assert result == {"dispatched": True, "intel_depth": 120}
        mock_recluster.apply_async.assert_called_once()
        mock_repair.apply_async.assert_called_once()
