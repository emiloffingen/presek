import json
import datetime
from unittest.mock import MagicMock, patch


class TestBackfillCoverArtTask:
    def test_backfill_queues_spaced_subtasks(self):
        import tasks

        rows = [
            {"cluster_id": "a1", "title": "A", "summary": ""},
            {"cluster_id": "b2", "title": "B", "summary": ""},
            {"cluster_id": "c3", "title": "C", "summary": ""},
        ]

        with patch.object(tasks, "db") as mock_db, \
             patch.object(tasks.backfill_cover_art_single_task, "apply_async") as mock_apply:
            mock_db.execute.return_value = rows
            tasks.backfill_cover_art_task()

        assert mock_apply.call_count == 3
        countdowns = [call.kwargs["countdown"] for call in mock_apply.call_args_list]
        args = [call.kwargs["args"] for call in mock_apply.call_args_list]
        assert countdowns == [0, 12, 24]
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


class TestSummarizeArticleTaskQuality:
    def test_uses_title_and_description_in_ai_prompt(self):
        import tasks

        with patch.object(tasks, "db") as mock_db, \
             patch.object(tasks, "_call_ai", return_value=({'summary': 'Чисто резиме.'}, "mistral")) as mock_call_ai, \
             patch.object(tasks, "clean_json_response", side_effect=lambda value: value), \
             patch.object(tasks, "invalidate_public_data_caches"), \
             patch.object(tasks, "record_task_event"):
            # Use a description > 200 chars to trigger AI path
            long_desc = "Опис со повеќе детали за настанот. " * 10
            mock_db.execute_one.return_value = {"description": long_desc}

            tasks.summarize_article_task("article-1", "Наслов на веста")

        prompt = mock_call_ai.call_args.args[0]
        assert "Наслов на веста" in prompt
        assert "Опис со повеќе детали за настанот." in prompt


class TestDailyBriefTaskQuality:
    def test_builds_cluster_level_context_for_daily_brief(self):
        import tasks

        cluster_articles = [
            {
                "cluster_id": "c1",
                "title": "Трамп најави нови царини",
                "description": "Главниот развој.",
                "summary": "Кратко резиме.",
                "source": "MIA",
                "category": "Свет",
                "topic": "Економија",
                "created_at": "2026-04-05T10:00:00",
            },
            {
                "cluster_id": "c1",
                "title": "Reuters акцентира на рокот и реакциите",
                "description": "Втор агол.",
                "summary": "",
                "source": "Reuters",
                "category": "Свет",
                "topic": "Економија",
                "created_at": "2026-04-05T10:10:00",
            },
        ]

        with patch.object(tasks, "db") as mock_db, \
             patch.object(tasks, "score_cluster_for_homepage", return_value=4.2):
            mock_db.execute.return_value = cluster_articles
            mock_db.execute_one.return_value = {
                "summary": "• Главен развој: Трамп најави царини\n• Контекст: Реакции на пазарите\n• Што следи: Се чека рокот",
                "perspectives": [
                    {"angle": "Различни акценти", "content": "Reuters повеќе го нагласува рокот."},
                    {"angle": "Што останува отворено", "content": "Не е јасно кога мерките ќе стапат на сила."},
                ],
            }

            clusters = tasks._load_daily_brief_clusters(limit=3)
            context = tasks._build_daily_brief_context(clusters)

        assert clusters
        assert clusters[0]["difference_point"]
        assert clusters[0]["open_point"]
        assert "### Кластер 1" in context
        assert "Водечки извор: MIA" in context
        assert "Разлики:" in context
        assert "Отворено:" in context


class TestProfileDeliveryTasks:
    def test_send_profile_briefings_updates_last_sent(self):
        import tasks

        rows = [
            {
                "sync_token": "sync-token-123",
                "target": "reader-feed",
                "morning_briefing": True,
                "profile_data": {"followedTopics": ["Политика"], "followedSources": []},
                "last_morning_sent_at": None,
            }
        ]

        with patch.object(tasks, "_load_active_delivery_rows", return_value=rows), \
             patch.object(tasks, "_select_profile_brief_clusters", return_value=[{"cluster_id": "lead-cluster", "title": "Lead story", "source": "MIA", "source_count": 2, "match_reason": "следена тема: Политика"}]), \
             patch.object(tasks, "_build_profile_briefing_message", return_value="Digest body"), \
             patch.object(tasks, "_record_delivery_tracking_event", return_value=11), \
             patch.object(tasks, "_send_ntfy_message", return_value=True) as mock_send, \
             patch.object(tasks, "db") as mock_db:
            tasks.send_profile_briefings_task()

        mock_send.assert_called_once()
        update_sql = mock_db.execute.call_args_list[-1].args[0]
        assert "last_morning_sent_at" in update_sql
        assert "event_id=11" in mock_send.call_args.kwargs["click_url"]

    def test_send_profile_weekly_digests_updates_last_sent(self):
        import tasks

        rows = [
            {
                "sync_token": "sync-token-123",
                "target": "reader-feed",
                "weekly_digest": True,
                "profile_data": {"followedTopics": ["Политика"], "followedSources": []},
                "last_weekly_sent_at": None,
            }
        ]

        with patch.object(tasks, "_load_active_delivery_rows", return_value=rows), \
             patch.object(tasks, "_select_profile_weekly_clusters", return_value=[{"cluster_id": "week-cluster", "title": "Week lead", "source": "MIA", "source_count": 4, "match_reason": "следена тема: Политика"}]), \
             patch.object(tasks, "_build_profile_weekly_digest_message", return_value="Weekly body"), \
             patch.object(tasks, "_record_delivery_tracking_event", return_value=22), \
             patch.object(tasks, "_send_ntfy_message", return_value=True) as mock_send, \
             patch.object(tasks, "db") as mock_db:
            tasks.send_profile_weekly_digests_task()

        mock_send.assert_called_once()
        update_sql = mock_db.execute.call_args_list[-1].args[0]
        assert "last_weekly_sent_at" in update_sql
        assert "event_id=22" in mock_send.call_args.kwargs["click_url"]

    def test_select_profile_weekly_clusters_prefers_items_with_real_digest_engagement(self):
        import tasks

        clusters = [
            {
                "cluster_id": "steady-cluster",
                "title": "Steady story",
                "source": "MIA",
                "source_count": 3,
                "category": "Политика",
                "topic": "Политика",
                "score": 4.8,
            },
            {
                "cluster_id": "engaged-cluster",
                "title": "Engaged story",
                "source": "Телма",
                "source_count": 2,
                "category": "Политика",
                "topic": "Политика",
                "score": 4.1,
            },
        ]

        with patch.object(tasks, "_load_weekly_digest_clusters", return_value=clusters), \
             patch.object(
                 tasks,
                 "_load_weekly_cluster_engagement",
                 return_value={
                     "engaged-cluster": {"sends": 4, "opens": 3, "clicks": 1, "open_rate": 0.75, "click_rate": 0.25, "engagement_score": 0.7},
                     "steady-cluster": {"sends": 4, "opens": 0, "clicks": 0, "open_rate": 0.0, "click_rate": 0.0, "engagement_score": 0.0},
                 },
             ):
            result = tasks._select_profile_weekly_clusters(
                {"followedTopics": ["Политика"], "followedSources": []},
                limit=2,
            )

        assert result[0]["cluster_id"] == "engaged-cluster"
        assert "силен одзив" in result[0]["match_reason"]

    def test_load_weekly_cluster_engagement_uses_send_metadata_cluster_ids(self):
        import tasks

        with patch.object(tasks, "db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {"id": 10, "cluster_id": "lead-cluster", "metadata": {"cluster_ids": ["lead-cluster", "second-cluster"]}},
                ],
                [
                    {"parent_event_id": 10, "event_type": "open"},
                    {"parent_event_id": 10, "event_type": "click"},
                ],
            ]
            result = tasks._load_weekly_cluster_engagement(days=30)

        assert result["lead-cluster"]["sends"] == 1
        assert result["lead-cluster"]["opens"] == 1
        assert result["lead-cluster"]["clicks"] == 1
        assert result["second-cluster"]["open_rate"] == 1.0

    def test_load_weekly_topic_engagement_uses_focus_topics_from_send_metadata(self):
        import tasks

        with patch.object(tasks, "db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {"id": 15, "metadata": {"focus_topics": ["Политика", "Економија"]}},
                ],
                [
                    {"parent_event_id": 15, "event_type": "open"},
                    {"parent_event_id": 15, "event_type": "click"},
                ],
            ]
            result = tasks._load_weekly_topic_engagement(days=30)

        assert result["Политика"]["open_rate"] == 1.0
        assert result["Економија"]["click_rate"] == 1.0

    def test_load_weekly_source_engagement_uses_focus_sources_from_send_metadata(self):
        import tasks

        with patch.object(tasks, "db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {"id": 21, "metadata": {"focus_sources": ["MIA", "Телма"]}},
                ],
                [
                    {"parent_event_id": 21, "event_type": "open"},
                    {"parent_event_id": 21, "event_type": "click"},
                ],
            ]
            result = tasks._load_weekly_source_engagement(days=30)

        assert result["MIA"]["open_rate"] == 1.0
        assert result["Телма"]["click_rate"] == 1.0

    def test_build_weekly_digest_sections_prioritizes_high_performing_followed_topics(self):
        import tasks

        clusters = [
            {
                "cluster_id": "politics-1",
                "title": "Political lead",
                "source": "MIA",
                "source_count": 4,
                "topic": "Политика",
                "category": "Политика",
                "match_score": 4.2,
                "match_reason": "следена тема: Политика",
            },
            {
                "cluster_id": "economy-1",
                "title": "Economy lead",
                "source": "Телма",
                "source_count": 3,
                "topic": "Економија",
                "category": "Економија",
                "match_score": 3.8,
                "match_reason": "следена тема: Економија",
            },
        ]

        sections = tasks._build_weekly_digest_sections(
            {"followedTopics": ["Политика", "Економија"], "followedSources": []},
            clusters,
            {"Политика": {"section_score": 0.8}, "Економија": {"section_score": 0.1}},
        )

        assert sections[1]["title"] == "Следена тема: Политика"
        assert "силен интерес" in sections[1]["subtitle"]

    def test_build_weekly_digest_sections_prioritizes_strong_source_section_over_weaker_topic_section(self):
        import tasks

        clusters = [
            {
                "cluster_id": "lead-1",
                "title": "Lead weekly story",
                "source": "MIA",
                "source_count": 4,
                "topic": "Политика",
                "category": "Политика",
                "match_score": 3.1,
                "match_reason": "следена тема: Политика",
            },
            {
                "cluster_id": "source-1",
                "title": "Source-led follow-up",
                "source": "Телма",
                "source_count": 3,
                "topic": "Свет",
                "category": "Свет",
                "match_score": 4.0,
                "match_reason": "следен извор: Телма",
            },
        ]

        sections = tasks._build_weekly_digest_sections(
            {"followedTopics": ["Политика"], "followedSources": ["Телма"]},
            clusters,
            {"Политика": {"section_score": 0.15}},
            {"Телма": {"section_score": 0.85}},
        )

        assert sections[1]["title"] == "Извори што ги следите"
        assert "Телма" in sections[1]["subtitle"]

    def test_build_profile_weekly_digest_message_renders_section_headings(self):
        import tasks

        clusters = [
            {
                "cluster_id": "lead-1",
                "title": "Lead weekly story",
                "source": "MIA",
                "source_count": 4,
                "match_reason": "следена тема: Политика",
                "cluster_summary": "Главен развој неделава.",
                "difference_point": "",
                "open_point": "",
            }
        ]

        with patch.object(tasks, "_load_weekly_topic_engagement", return_value={"Политика": {"section_score": 0.8}}), \
             patch.object(tasks, "_load_weekly_source_engagement", return_value={}), \
             patch.object(tasks, "_build_weekly_digest_sections", return_value=[
                 {"title": "Што најмногу се помести", "subtitle": "главен неделен развој", "clusters": clusters}
             ]):
            message = tasks._build_profile_weekly_digest_message(
                {"followedTopics": ["Политика"], "followedSources": []},
                clusters,
            )

        assert "## Што најмногу се помести" in message
        assert "Lead weekly story" in message

    def test_select_profile_weekly_clusters_avoids_duplicate_heavy_same_topic_mix(self):
        import tasks

        clusters = [
            {
                "cluster_id": "p1",
                "title": "Политички развој 1",
                "source": "MIA",
                "source_count": 4,
                "topic": "Политика",
                "category": "Политика",
                "score": 4.8,
            },
            {
                "cluster_id": "p2",
                "title": "Политички развој 2",
                "source": "Reuters",
                "source_count": 3,
                "topic": "Политика",
                "category": "Политика",
                "score": 4.1,
            },
            {
                "cluster_id": "e1",
                "title": "Економски развој",
                "source": "Телма",
                "source_count": 3,
                "topic": "Економија",
                "category": "Економија",
                "score": 3.9,
            },
        ]

        profile = {"followedTopics": ["Политика", "Економија"], "followedSources": []}

        with patch.object(tasks, "_load_weekly_digest_clusters", return_value=clusters), \
             patch.object(tasks, "_load_weekly_cluster_engagement", return_value={}):
            result = tasks._select_profile_weekly_clusters(profile, limit=3)

        returned_topics = [item["topic"] for item in result]
        assert "Економија" in returned_topics
        assert returned_topics.count("Политика") <= 1

    def test_select_profile_brief_clusters_prefers_richer_editorial_cluster(self):
        import tasks

        clusters = [
            {
                "cluster_id": "thin-1",
                "title": "Краток развој",
                "source": "Makfax",
                "source_count": 2,
                "topic": "Политика",
                "category": "Политика",
                "score": 3.2,
                "difference_point": "",
                "open_point": "",
                "cluster_summary": "",
                "other_titles": [],
            },
            {
                "cluster_id": "rich-1",
                "title": "Развој со различни акценти",
                "source": "MIA",
                "source_count": 4,
                "topic": "Политика",
                "category": "Политика",
                "score": 3.0,
                "difference_point": "Изворите се разликуваат околу рокот.",
                "open_point": "Останува да се потврди точниот датум.",
                "cluster_summary": "Главниот развој со повеќе контекст.",
                "other_titles": ["Агол 1", "Агол 2"],
            },
        ]

        profile = {"followedTopics": ["Политика"], "followedSources": []}

        with patch.object(tasks, "_load_daily_brief_clusters", return_value=clusters):
            result = tasks._select_profile_brief_clusters(profile, limit=2)

        assert result[0]["cluster_id"] == "rich-1"

    def test_send_profile_breaking_alerts_tracks_alerted_cluster(self):
        import tasks

        rows = [
            {
                "sync_token": "sync-token-123",
                "target": "reader-feed",
                "breaking_topics": True,
                "breaking_sources": False,
                "profile_data": {"followedTopics": ["Политика"], "followedSources": []},
                "last_alert_cluster_ids": ["old-cluster"],
                "last_alert_context": {},
                "last_breaking_sent_at": None,
            }
        ]
        candidate = {
            "cluster_id": "new-cluster",
            "title": "Breaking story",
            "source": "MIA",
            "source_count": 3,
            "match_reason": "следена тема: Политика",
            "alert_label": "Итно ажурирање",
            "alert_reason": "се појави нов доверлив извор или значаен развој",
            "alert_tags": "rotating_light,newspaper",
            "throttle_keys": ["cluster:new-cluster", "topic:Политика"],
            "cluster_summary": "Главниот развој.",
        }

        with patch.object(tasks, "_load_active_delivery_rows", return_value=rows), \
             patch.object(tasks, "_select_breaking_cluster_for_profile", return_value=candidate), \
             patch.object(tasks, "_record_delivery_tracking_event", return_value=33), \
             patch.object(tasks, "_send_ntfy_message", return_value=True) as mock_send, \
             patch.object(tasks, "db") as mock_db:
            tasks.send_profile_breaking_alerts_task()

        mock_send.assert_called_once()
        params = mock_db.execute.call_args_list[-1].args[1]
        assert "new-cluster" in params[0]
        assert "topic:Политика" in json.loads(params[1])
        assert "event_id=33" in mock_send.call_args.kwargs["click_url"]

    def test_select_breaking_cluster_skips_recent_topic_cooldown(self):
        import tasks
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_iso = now.isoformat()
        cluster = {
            "cluster_id": "new-cluster",
            "title": "Breaking story",
            "source": "MIA",
            "source_count": 3,
            "score": 5.2,
            "category": "Политика",
            "topic": "Политика",
            "created_at": recent_iso,
        }
        freshness = {"refresh_needed": True, "freshness_score": 2.1, "reasons": ["new_sources"]}

        with patch.object(tasks, "_load_recent_breaking_clusters", return_value=[cluster]), \
             patch.object(tasks, "_load_cluster_alert_material", return_value=([{"title": "a", "source": "MIA", "created_at": recent_iso}], now)), \
             patch.object(tasks, "_load_delivery_kind_performance", return_value={}), \
             patch.object(tasks, "_load_breaking_target_performance", return_value={"topics": {}, "sources": {}}), \
             patch.object(tasks, "assess_cluster_synthesis_freshness", return_value=freshness):
            candidate = tasks._select_breaking_cluster_for_profile(
                {"followedTopics": ["Политика"], "followedSources": []},
                [],
                alert_context={"topic:Политика": recent_iso},
                last_breaking_sent_at=None,
                include_topics=True,
                include_sources=False,
            )

        assert candidate is None

    def test_select_breaking_cluster_allows_material_refresh_after_seen(self):
        import tasks
        older = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)).isoformat()
        cluster = {
            "cluster_id": "same-cluster",
            "title": "Breaking story",
            "source": "MIA",
            "source_count": 4,
            "score": 5.8,
            "category": "Политика",
            "topic": "Политика",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        freshness = {"refresh_needed": True, "freshness_score": 2.6, "reasons": ["new_sources", "new_numbers"]}

        with patch.object(tasks, "_load_recent_breaking_clusters", return_value=[cluster]), \
             patch.object(tasks, "_load_cluster_alert_material", return_value=([{"title": "a", "source": "MIA", "created_at": cluster["created_at"]}], older)), \
             patch.object(tasks, "_load_delivery_kind_performance", return_value={}), \
             patch.object(tasks, "_load_breaking_target_performance", return_value={"topics": {}, "sources": {}}), \
             patch.object(tasks, "assess_cluster_synthesis_freshness", return_value=freshness):
            candidate = tasks._select_breaking_cluster_for_profile(
                {"followedTopics": ["Политика"], "followedSources": []},
                ["same-cluster"],
                alert_context={"cluster:same-cluster": older},
                last_breaking_sent_at=older,
                include_topics=True,
                include_sources=False,
            )

        assert candidate is not None
        assert candidate["cluster_id"] == "same-cluster"
        assert candidate["alert_label"] == "Итно ажурирање"

    def test_classify_alert_candidate_becomes_stricter_when_breaking_engagement_is_weak(self):
        import tasks

        candidate = tasks._classify_alert_candidate(
            {"cluster_id": "weak-1", "score": 2.8},
            {"freshness_score": 1.2, "reasons": ["multiple_new_reports"]},
            ["Политика"],
            [],
            {"breaking": {"sends": 12, "open_rate": 0.25, "click_rate": 0.08}},
        )

        assert candidate["engagement_label"] == "Слаб одзив"
        assert candidate["score_adjustment"] < 0
        assert candidate["topic_gap_minutes"] > 360

    def test_classify_alert_candidate_allows_faster_high_signal_alerts_when_engagement_is_strong(self):
        import tasks

        candidate = tasks._classify_alert_candidate(
            {"cluster_id": "strong-1", "score": 5.9},
            {"freshness_score": 2.2, "reasons": ["new_numbers"]},
            ["Политика"],
            ["MIA"],
            {"breaking": {"sends": 10, "open_rate": 0.61, "click_rate": 0.28}},
        )

        assert candidate["engagement_label"] == "Силен одзив"
        assert candidate["score_adjustment"] > 0
        assert candidate["min_gap_minutes"] < 60

    def test_classify_alert_candidate_boosts_topic_with_strong_engagement_history(self):
        import tasks

        candidate = tasks._classify_alert_candidate(
            {"cluster_id": "topic-strong", "score": 5.1},
            {"freshness_score": 1.9, "reasons": ["new_angle"]},
            ["Политика"],
            [],
            {},
            {"topics": {"Политика": {"sends": 3, "open_rate": 0.67, "click_rate": 0.25}}, "sources": {}},
        )

        assert candidate["engagement_label"] == "Силен одзив за следеното"
        assert candidate["score_adjustment"] > 0
        assert "силен одзив" in candidate["alert_reason"]

    def test_classify_alert_candidate_slows_weak_source_with_no_clicks(self):
        import tasks

        candidate = tasks._classify_alert_candidate(
            {"cluster_id": "source-weak", "score": 3.2},
            {"freshness_score": 1.3, "reasons": ["multiple_new_reports"]},
            [],
            ["MIA"],
            {},
            {"topics": {}, "sources": {"MIA": {"sends": 4, "open_rate": 0.15, "click_rate": 0.0}}},
        )

        assert candidate["engagement_label"] == "Слаб одзив за следеното"
        assert candidate["score_adjustment"] < 0
        assert candidate["source_gap_minutes"] > 240

    def test_load_breaking_target_performance_aggregates_topics_and_sources(self):
        import tasks

        with patch.object(tasks, "db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {"id": 7, "metadata": {"matched_topics": ["Политика"], "matched_sources": ["MIA"]}},
                ],
                [
                    {"parent_event_id": 7, "event_type": "open"},
                    {"parent_event_id": 7, "event_type": "click"},
                ],
            ]
            result = tasks._load_breaking_target_performance(days=30)

        assert result["topics"]["Политика"]["open_rate"] == 1.0
        assert result["sources"]["MIA"]["click_rate"] == 1.0
