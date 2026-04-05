from unittest.mock import MagicMock, patch


class TestBackfillCoverArtTask:
    def test_backfill_queues_spaced_subtasks(self):
        import tasks

        rows = [
            {"cluster_id": "a1", "title": "A"},
            {"cluster_id": "b2", "title": "B"},
            {"cluster_id": "c3", "title": "C"},
        ]

        with patch.object(tasks, "db") as mock_db, \
             patch.object(tasks.backfill_cover_art_single_task, "apply_async") as mock_apply:
            mock_db.execute.return_value = rows
            tasks.backfill_cover_art_task()

        assert mock_apply.call_count == 3
        countdowns = [call.kwargs["countdown"] for call in mock_apply.call_args_list]
        args = [call.kwargs["args"] for call in mock_apply.call_args_list]
        assert countdowns == [0, 4, 8]
        assert args == [("a1", "A"), ("b2", "B"), ("c3", "C")]
