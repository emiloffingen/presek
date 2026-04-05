import json
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


class TestSynthesizeClusterTaskQuality:
    def test_normalizes_ai_summary_and_perspectives_before_store(self):
        import tasks

        article_rows = [
            {
                "title": "Трамп: Вторник, 20:00 часот по источно време",
                "description": "Американскиот претседател најави важно обраќање за царините.",
                "source": "МИА",
                "link": "https://example.com/1",
                "created_at": "2026-04-05T12:00:00",
                "category": "Свет",
            },
            {
                "title": "Трамп: Вторник, 20:00 часот по Источно време",
                "description": "Повеќе извори пренесуваат дека темата се однесува на царини.",
                "source": "DW",
                "link": "https://example.com/2",
                "created_at": "2026-04-05T11:00:00",
                "category": "Свет",
            },
        ]

        ai_payload = {
            "summary": "Статии:\n• Главен развој: Трамп: Вторник, 20:00 часот по источно време\n• Главен развој: Трамп: Вторник, 20:00 часот по источно време",
            "perspectives": [
                {"angle": "Перспектива", "content": "Повеќето извори се вртат околу царините и рокот за обраќање."},
                {"angle": "Перспектива", "content": "Разликите најмногу се во акцентот и формулацијата."},
            ],
        }

        with patch.object(tasks, "db") as mock_db, \
             patch.object(tasks, "_call_ai", return_value=(ai_payload, "mistral")), \
             patch.object(tasks, "clean_json_response", side_effect=lambda value: value), \
             patch.object(tasks, "generate_cover_art", return_value=None), \
             patch.object(tasks, "invalidate_cluster_caches"), \
             patch.object(tasks, "record_task_event"):
            mock_db.execute.side_effect = [article_rows, None]
            mock_db.execute_one.return_value = {"dummy": 1}

            tasks.synthesize_cluster_task("cluster-1", "content")

        insert_call = mock_db.execute.call_args_list[1]
        stored_summary = insert_call.args[1][1]
        stored_perspectives = json.loads(insert_call.args[1][2])

        assert "Статии" not in stored_summary
        assert stored_summary.count("Главен развој") == 1
        assert stored_perspectives[0]["angle"] == "Заедничка линија"
        assert stored_perspectives[1]["angle"] == "Различни акценти"
