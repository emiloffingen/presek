from unittest.mock import patch

from tasks.intelligence import (
    backfill_historical_article_summaries_task,
    summarize_article_task,
)


class TestHistoricalSummaryBackfill:
    def test_skips_when_backlog_high(self):
        with patch("tasks.intelligence.intelligence_secondary_deferred", return_value=True):
            result = backfill_historical_article_summaries_task()
        assert result == {"skipped": True, "reason": "backlog_high"}

    def test_enqueues_local_batches_and_advances_cursor(self):
        mock_redis = patch("tasks.intelligence.redis_client")
        with (
            patch("tasks.intelligence.intelligence_secondary_deferred", return_value=False),
            patch("core.llm_router._local_model_available", return_value=True),
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence._dispatch_batched") as mock_dispatch,
            mock_redis as redis_mock,
        ):
            redis_mock.get.return_value = "100"
            mock_db.execute.return_value = [{"id": 101}, {"id": 102}]
            result = backfill_historical_article_summaries_task(limit=50)

        assert result == {"enqueued": 2, "cursor_id": 102, "complete": False}
        mock_dispatch.assert_called_once()
        redis_mock.set.assert_called_once_with("backfill:article_summaries:cursor", "102")

    def test_runs_when_queue_below_secondary_defer_limit(self):
        mock_redis = patch("tasks.intelligence.redis_client")
        with (
            patch("tasks.intelligence.intelligence_secondary_deferred", return_value=False),
            patch("core.llm_router._local_model_available", return_value=True),
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence._dispatch_batched") as mock_dispatch,
            mock_redis as redis_mock,
        ):
            redis_mock.get.return_value = None
            mock_db.execute.return_value = [{"id": 1}]
            result = backfill_historical_article_summaries_task(limit=1)

        assert result == {"enqueued": 1, "cursor_id": 1, "complete": False}
        mock_dispatch.assert_called_once()

    def test_scales_dispatch_limit_with_queue_headroom(self):
        mock_redis = patch("tasks.intelligence.redis_client")
        with (
            patch("tasks.intelligence.intelligence_secondary_deferred", return_value=False),
            patch("tasks.intelligence.get_celery_queue_depth", return_value=92),
            patch("core.llm_router._local_model_available", return_value=True),
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence._dispatch_batched") as mock_dispatch,
            mock_redis as redis_mock,
        ):
            redis_mock.get.return_value = "80"
            mock_db.execute.return_value = [{"id": i} for i in range(81, 321)]
            result = backfill_historical_article_summaries_task()

        assert result["enqueued"] == 240
        assert result["cursor_id"] == 320
        mock_dispatch.assert_called_once()
        article_ids = mock_dispatch.call_args.args[1]
        assert len(article_ids) == 240


class TestLocalOnlySummarize:
    def test_uses_local_provider_override(self):
        with (
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence._call_ai", return_value=({"summary": "Rezime."}, "local")) as mock_call,
            patch("tasks.intelligence.clean_json_response", side_effect=lambda value: value),
            patch("tasks.intelligence.validate_person_names", side_effect=lambda value: value),
            patch("tasks.intelligence.invalidate_public_data_caches"),
        ):
            mock_db.execute_one.return_value = {
                "title": "Naslov",
                "description": "Opis",
                "full_content": "",
                "topic": "vesti",
                "category": "Srbija",
            }
            summarize_article_task(123, local_only=True)

        mock_call.assert_called_once()
        _args, kwargs = mock_call.call_args
        assert kwargs["provider_override"] == "local"
        assert kwargs["exclude_providers"] == ["mistral_small", "mistral_large", "nvidia"]
