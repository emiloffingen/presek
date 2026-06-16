from unittest.mock import MagicMock, patch

from tasks.utils import invalidate_cluster_caches, invalidate_public_data_caches_debounced


class TestCacheInvalidation:
    @patch("tasks.utils.delete_cache_prefix")
    @patch("tasks.utils.delete_cache")
    @patch("tasks.utils.invalidate_public_data_caches")
    def test_invalidate_cluster_caches_uses_current_detail_prefix(
        self, mock_public, mock_delete, mock_delete_prefix
    ):
        invalidate_cluster_caches("cluster-123")

        mock_delete.assert_called_once_with("cluster:detail:cluster-123")
        mock_delete_prefix.assert_called_once_with("api:cluster:detail:v3:cluster-123")
        mock_public.assert_called_once()

    @patch("tasks.utils.invalidate_public_data_caches")
    @patch("tasks.utils.redis_client")
    def test_debounced_public_cache_invalidation_skips_repeat(self, mock_redis, mock_public):
        mock_redis.set.side_effect = [True, False]

        assert invalidate_public_data_caches_debounced() is True
        assert invalidate_public_data_caches_debounced() is False

        mock_public.assert_called_once()

    @patch("tasks.utils.invalidate_public_data_caches")
    @patch("tasks.utils.redis_client")
    def test_debounced_public_cache_invalidation_force(self, mock_redis, mock_public):
        assert invalidate_public_data_caches_debounced(force=True) is True

        mock_redis.set.assert_not_called()
        mock_public.assert_called_once()


class TestAutoSummarizeOptimization:
    @patch("tasks.utils.synthesis_dispatch_deferred", return_value=False)
    @patch("tasks.utils.pipeline_backpressure_active", return_value=False)
    @patch("tasks.intelligence.synthesize_cluster_task.apply_async")
    @patch("tasks.utils.get_celery_queue_depth", return_value=0)
    @patch("core.database.db_manager")
    def test_auto_summarize_skips_fresh_summaries_and_backfill(
        self, mock_db, _mock_depth, mock_apply_async, _mock_backpressure, _mock_synthesis_deferred
    ):
        from core.ai_engine import auto_summarize_top_clusters

        mock_db.execute.side_effect = [
            [
                {
                    "cluster_id": "fresh",
                    "source": "A",
                    "title": "T1",
                    "summary": "S1",
                    "ingested_at": "2026-06-09T10:00:00Z",
                    "created_at": "2026-06-09T10:00:00Z",
                },
                {
                    "cluster_id": "fresh",
                    "source": "B",
                    "title": "T2",
                    "summary": "S2",
                    "ingested_at": "2026-06-09T10:00:00Z",
                    "created_at": "2026-06-09T10:00:00Z",
                },
                {
                    "cluster_id": "stale",
                    "source": "A",
                    "title": "T3",
                    "summary": "S3",
                    "ingested_at": "2026-06-09T10:00:00Z",
                    "created_at": "2026-06-09T10:00:00Z",
                },
                {
                    "cluster_id": "stale",
                    "source": "B",
                    "title": "T4",
                    "summary": "S4",
                    "ingested_at": "2026-06-09T10:00:00Z",
                    "created_at": "2026-06-09T10:00:00Z",
                },
            ],
            [{"cluster_id": "fresh"}],
        ]

        auto_summarize_top_clusters()

        assert mock_apply_async.call_count == 1
        assert mock_apply_async.call_args[0][0][0] == "stale"

    @patch("tasks.intelligence.synthesize_cluster_task.apply_async")
    @patch("tasks.utils.get_celery_queue_depth", return_value=250)
    @patch("core.database.db_manager")
    def test_auto_summarize_skips_when_queue_backlogged(self, mock_db, _mock_depth, mock_apply_async):
        from core.ai_engine import auto_summarize_top_clusters

        auto_summarize_top_clusters()

        mock_db.execute.assert_not_called()
        mock_apply_async.assert_not_called()


class TestPublicArticlePayload:
    def test_list_payload_omits_full_content(self):
        from routes.news import _public_article_payload

        payload = _public_article_payload(
            {
                "id": 1,
                "cluster_id": "abc",
                "title": "Test",
                "full_content": "x" * 5000,
            }
        )
        assert "full_content" not in payload

    def test_detail_payload_includes_full_content(self):
        from routes.news import _public_article_payload

        payload = _public_article_payload(
            {
                "id": 1,
                "cluster_id": "abc",
                "title": "Test",
                "full_content": "body",
            },
            include_full_content=True,
        )
        assert payload["full_content"] == "body"
