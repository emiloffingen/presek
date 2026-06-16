from unittest.mock import patch

from tasks.intelligence import (
    _HISTORICAL_SUMMARY_CURSOR_KEY,
    _HISTORICAL_SUMMARY_LOCK_KEY,
    backfill_historical_article_summaries_task,
    schedule_backfill_historical_summaries_task,
    summarize_article_task,
)


class TestHistoricalSummaryBackfill:
    def test_skips_when_backlog_high(self):
        with patch("tasks.intelligence.backfill.intelligence_secondary_deferred", return_value=True):
            result = backfill_historical_article_summaries_task()
        assert result == {"skipped": True, "reason": "backlog_high"}

    def test_selects_oldest_unsummarized_without_cursor_skip(self):
        mock_redis = patch("tasks.intelligence.backfill.redis_client")
        with (
            patch("tasks.intelligence.backfill.intelligence_secondary_deferred", return_value=False),
            patch("core.llm_router._local_model_available", return_value=True),
            patch("tasks.intelligence.backfill.db") as mock_db,
            patch("tasks.intelligence.backfill._dispatch_batched") as mock_dispatch,
            mock_redis as redis_mock,
        ):
            mock_db.execute.return_value = [{"id": 124}, {"id": 125}]
            result = backfill_historical_article_summaries_task(limit=50)

        sql, params = mock_db.execute.call_args.args[:2]
        assert "id >" not in sql
        assert params == (50,)
        assert result == {"enqueued": 2, "high_water": 125, "complete": False}
        mock_dispatch.assert_called_once()
        redis_mock.set.assert_called_once_with(_HISTORICAL_SUMMARY_CURSOR_KEY, "125")

    def test_runs_when_queue_below_secondary_defer_limit(self):
        with (
            patch("tasks.intelligence.backfill.intelligence_secondary_deferred", return_value=False),
            patch("core.llm_router._local_model_available", return_value=True),
            patch("tasks.intelligence.backfill.db") as mock_db,
            patch("tasks.intelligence.backfill._dispatch_batched") as mock_dispatch,
        ):
            mock_db.execute.return_value = [{"id": 1}]
            result = backfill_historical_article_summaries_task(limit=1)

        assert result == {"enqueued": 1, "high_water": 1, "complete": False}
        mock_dispatch.assert_called_once()

    def test_scales_dispatch_limit_with_queue_headroom(self):
        with (
            patch("tasks.intelligence.backfill.intelligence_secondary_deferred", return_value=False),
            patch("tasks.intelligence.backfill.get_celery_queue_depth", return_value=92),
            patch("core.llm_router._local_model_available", return_value=True),
            patch("tasks.intelligence.backfill.db") as mock_db,
            patch("tasks.intelligence.backfill._dispatch_batched") as mock_dispatch,
            patch("tasks.intelligence.backfill.redis_client") as redis_mock,
        ):
            mock_db.execute.return_value = [{"id": i} for i in range(81, 321)]
            result = backfill_historical_article_summaries_task()

        assert result["enqueued"] == 240
        assert result["high_water"] == 320
        mock_dispatch.assert_called_once()
        article_ids = mock_dispatch.call_args.args[1]
        assert len(article_ids) == 240
        redis_mock.set.assert_called_once_with(_HISTORICAL_SUMMARY_CURSOR_KEY, "320")

    def test_scheduler_runs_inline_with_lock(self):
        with (
            patch("tasks.intelligence.backfill.intelligence_secondary_deferred", return_value=False),
            patch("core.llm_router._local_model_available", return_value=True),
            patch("tasks.intelligence.backfill.acquire_task_lock", return_value=True) as mock_lock,
            patch("tasks.intelligence.backfill.release_task_lock") as mock_release,
            patch(
                "tasks.intelligence.backfill.backfill_historical_article_summaries_task",
                return_value={"enqueued": 10, "high_water": 42, "complete": False},
            ) as mock_backfill,
        ):
            result = schedule_backfill_historical_summaries_task()

        mock_lock.assert_called_once_with(_HISTORICAL_SUMMARY_LOCK_KEY, 1200)
        mock_backfill.assert_called_once_with()
        mock_release.assert_called_once_with(_HISTORICAL_SUMMARY_LOCK_KEY)
        assert result == {"enqueued": 10, "high_water": 42, "complete": False}


class TestLocalOnlySummarize:
    def test_uses_local_provider_override(self):
        with (
            patch("tasks.intelligence.summarization.db") as mock_db,
            patch("tasks.intelligence.summarization._call_ai", return_value=({"summary": "Rezime."}, "local")) as mock_call,
            patch("tasks.intelligence.summarization.clean_json_response", side_effect=lambda value: value),
            patch("tasks.intelligence.summarization.validate_person_names", side_effect=lambda value: value),
            patch("tasks.intelligence.summarization.invalidate_public_data_caches"),
        ):
            mock_db.execute_one.return_value = {
                "title": "Naslov",
                "description": "Opis",
                "full_content": "",
                "topic": "vesti",
                "category": "Srbija",
                "summary": None,
            }
            summarize_article_task(123, local_only=True)

        mock_call.assert_called_once()
        _args, kwargs = mock_call.call_args
        assert kwargs["provider_override"] == "local"
        assert kwargs["exclude_providers"] == ["mistral_small", "mistral_large", "nvidia"]

    def test_skips_when_summary_already_exists(self):
        with (
            patch("tasks.intelligence.summarization.db") as mock_db,
            patch("tasks.intelligence.summarization._call_ai") as mock_call,
        ):
            mock_db.execute_one.return_value = {
                "title": "Naslov",
                "description": "Opis",
                "full_content": "",
                "topic": "vesti",
                "category": "Srbija",
                "summary": "Postojeci rezime.",
            }
            summarize_article_task(123, local_only=True)

        mock_call.assert_not_called()
