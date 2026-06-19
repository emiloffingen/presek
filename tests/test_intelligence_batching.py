from unittest.mock import MagicMock, patch

from tasks.intelligence import _dispatch_batched, backfill_cluster_summaries_task, generate_cluster_metadata_task


class TestIntelligenceBatching:
    def test_dispatch_batched_chunks_large_id_lists(self):
        task = MagicMock()
        ids = list(range(45))

        _dispatch_batched(task, ids, batch_size=20)

        assert task.delay.call_count == 3
        assert task.delay.call_args_list[0].args[0] == ids[:20]
        assert task.delay.call_args_list[1].args[0] == ids[20:40]
        assert task.delay.call_args_list[2].args[0] == ids[40:45]

    def test_backfill_skips_when_queue_backlogged(self):
        with (
            patch("tasks.intelligence.backfill._queue_backlog_high", return_value=True),
            patch.object(backfill_cluster_summaries_task, "apply_async") as mock_apply,
        ):
            backfill_cluster_summaries_task(days=7, lang="mk", offset=12)

        mock_apply.assert_not_called()

    def test_metadata_batches_target_clusters(self):
        with (
            patch("tasks.intelligence.metadata._queue_backlog_high", return_value=False),
            patch("tasks.intelligence.metadata.db") as mock_db,
            patch("tasks.intelligence.metadata.extract_cluster_tags_locally", return_value=["tag"]),
            patch("tasks.intelligence.metadata.filter_cluster_tags", return_value=["tag"]),
            patch("tasks.intelligence.metadata._compute_centroid_from_values", return_value=None),
            patch("nlp.image_quality.select_representative_image", return_value=None),
            patch("tasks.intelligence.metadata.generate_local_placeholder", return_value="<svg/>"),
            patch("tasks.intelligence.metadata.invalidate_public_data_caches"),
            patch("tasks.intelligence.metadata.schedule_task_once", return_value=True) as mock_schedule,
        ):
            mock_db.execute.return_value = [
                {
                    "cluster_id": "c1",
                    "sources": ["A"],
                    "titles": ["Title"],
                    "topics": ["topic"],
                    "dominant_category": "News",
                    "embeddings": [],
                }
            ]
            mock_db.execute_one.side_effect = [None, None]

            generate_cluster_metadata_task(
                target_clusters=[f"c{i}" for i in range(30)],
            )

        pending = mock_schedule.call_args.kwargs["kwargs"]["target_clusters"]
        assert pending == [f"c{i}" for i in range(25, 30)]
