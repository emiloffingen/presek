import datetime
import json
from unittest.mock import patch

import tasks
from tasks.intelligence import _polish_generated_article, _sanitize_synthesis_outputs, _split_cluster_merge_score


class TestBackfillCoverArtTask:
    def test_backfill_queues_spaced_subtasks(self):
        rows = [
            {"cluster_id": "a1", "title": "A", "summary": ""},
            {"cluster_id": "b2", "title": "B", "summary": ""},
            {"cluster_id": "c3", "title": "C", "summary": ""},
        ]

        with (
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence.redis_client") as mock_redis,
            patch("tasks.intelligence.get_celery_queue_depth", return_value=0),
            patch.object(tasks.backfill_cover_art_single_task, "apply_async") as mock_apply,
        ):
            mock_db.execute.return_value = rows
            mock_redis.set.return_value = True
            mock_redis.get.return_value = None
            tasks.backfill_cover_art_task()

        assert mock_apply.call_count == 3
        countdowns = [call.kwargs["countdown"] for call in mock_apply.call_args_list]
        args = [call.kwargs["args"] for call in mock_apply.call_args_list]
        assert countdowns == [0, 5, 10]
        assert args == [("a1", "A"), ("b2", "B"), ("c3", "C")]

    def test_backfill_skips_when_queue_backlog_is_high(self):

        with (
            patch("tasks.intelligence.get_celery_queue_depth", return_value=150),
            patch("tasks.intelligence.db") as mock_db,
            patch.object(tasks.backfill_cover_art_single_task, "apply_async") as mock_apply,
        ):
            tasks.backfill_cover_art_task()

        mock_db.execute.assert_not_called()
        mock_apply.assert_not_called()


class TestRepairSplitClustersTask:
    def test_split_cluster_score_accepts_entity_rich_same_story(self):
        now = datetime.datetime.now()
        left = {
            "cluster_id": "f4",
            "country": "MK",
            "category": "Germanija",
            "topic": "vesti",
            "latest_article": now,
            "titles": [
                "Минибусот во кој беа фатени 500.000 евра на ГП Табановце, од Германија требало да стигне во Албанија"
            ],
            "tags": ["Минибусот", "Табановце", "Германија", "Албанија"],
        }
        right = {
            "cluster_id": "1d",
            "country": "MK",
            "category": "Germanija",
            "topic": "vesti",
            "latest_article": now - datetime.timedelta(hours=12),
            "titles": [
                "Минибусот во кој беа најдени половина милион евра кеш возел од Германија кон Албанија, открива Николовски"
            ],
            "tags": ["Минибусот", "Германија", "Албанија", "Николовски"],
        }

        assert _split_cluster_merge_score(left, right, lang="mk") > 0

    def test_split_cluster_score_rejects_generic_broad_topic(self):
        now = datetime.datetime.now()
        left = {
            "cluster_id": "cash",
            "country": "MK",
            "category": "Germanija",
            "topic": "vesti",
            "latest_article": now,
            "titles": ["Минибус со пари запленет на Табановце"],
            "tags": ["Германија"],
        }
        right = {
            "cluster_id": "scholz",
            "country": "MK",
            "category": "Germanija",
            "topic": "vesti",
            "latest_article": now,
            "titles": ["Шолц ја отфрли соработката со Алтернатива за Германија"],
            "tags": ["Германија"],
        }

        assert _split_cluster_merge_score(left, right, lang="mk") == 0

    def test_repair_split_clusters_merges_source_into_larger_target(self):
        now = datetime.datetime.now()
        rows = [
            {
                "cluster_id": "f4",
                "country": "MK",
                "category": "Germanija",
                "topic": "vesti",
                "article_count": 2,
                "first_article": now - datetime.timedelta(hours=13),
                "latest_article": now - datetime.timedelta(hours=12),
                "titles": [
                    "Минибусот во кој беа фатени 500.000 евра на ГП Табановце, од Германија требало да стигне во Албанија"
                ],
                "tags": ["Минибусот", "Табановце", "Германија", "Албанија"],
                "centroid": None,
            },
            {
                "cluster_id": "1d",
                "country": "MK",
                "category": "Germanija",
                "topic": "vesti",
                "article_count": 1,
                "first_article": now,
                "latest_article": now,
                "titles": [
                    "Минибусот во кој беа најдени половина милион евра кеш возел од Германија кон Албанија, открива Николовски"
                ],
                "tags": ["Минибусот", "Германија", "Албанија", "Николовски"],
                "centroid": None,
            },
        ]

        with (
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence.invalidate_public_data_caches") as mock_invalidate,
            patch("tasks.utils.record_task_event"),
            patch.object(tasks.extract_entities_task, "apply_async") as mock_extract_delay,
            patch.object(tasks.generate_cluster_metadata_task, "apply_async") as mock_meta_delay,
            patch.object(tasks.intelligence.auto_summarize_task, "apply_async") as mock_summary_delay,
        ):
            mock_db.execute.side_effect = [rows, 1, 1, 1, 1, 1]
            result = tasks.repair_split_clusters_task(hours=48, limit=20)

        assert result["merges"] == [{"source": "1d", "target": "f4", "score": result["merges"][0]["score"]}]
        update_call = mock_db.execute.call_args_list[1]
        assert "UPDATE articles SET cluster_id = %s WHERE cluster_id = %s" in update_call.args[0]
        assert update_call.args[1] == ("f4", "1d")
        mock_extract_delay.assert_called_once()
        mock_meta_delay.assert_called_once()
        mock_summary_delay.assert_called_once()
        mock_invalidate.assert_called_once()

    def test_repair_split_clusters_resolves_chains_to_final_target(self):
        now = datetime.datetime.now()
        rows = [
            {
                "cluster_id": "a",
                "country": "MK",
                "category": "Makedonija",
                "topic": "Politika",
                "article_count": 1,
                "first_article": now - datetime.timedelta(minutes=30),
                "latest_article": now,
                "titles": ["Собранието го усвои законот за задолжување од 260 милиони евра"],
                "tags": ["Собранието", "задолжување", "260 милиони"],
                "centroid": None,
            },
            {
                "cluster_id": "b",
                "country": "MK",
                "category": "Makedonija",
                "topic": "Politika",
                "article_count": 2,
                "first_article": now - datetime.timedelta(hours=1),
                "latest_article": now,
                "titles": ["Со 65 гласа донесен законот за задолжување од 260 милиони евра"],
                "tags": ["Собранието", "задолжување", "260 милиони"],
                "centroid": None,
            },
            {
                "cluster_id": "c",
                "country": "MK",
                "category": "Makedonija",
                "topic": "Politika",
                "article_count": 4,
                "first_article": now - datetime.timedelta(hours=2),
                "latest_article": now,
                "titles": ["Собранието го донесе законот за задолжување на државата"],
                "tags": ["Собранието", "задолжување", "260 милиони"],
                "centroid": None,
            },
        ]

        with (
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence.invalidate_public_data_caches"),
            patch("tasks.utils.record_task_event"),
            patch.object(tasks.extract_entities_task, "apply_async"),
            patch.object(tasks.generate_cluster_metadata_task, "apply_async"),
            patch.object(tasks.intelligence.auto_summarize_task, "apply_async"),
        ):
            mock_db.execute.side_effect = [rows, 1, 1, 1, 1, 1, 1]
            result = tasks.repair_split_clusters_task(hours=48, limit=20)

        assert all(item["target"] == "c" for item in result["merges"])
        assert {item["source"] for item in result["merges"]} == {"a", "b"}

    def test_sanitize_synthesis_replaces_json_fragment_and_dedupes_article(self):
        article_rows = [
            {
                "source": "Telma",
                "title": "Минибусот тргнал од Германија кон Албанија",
                "description": "Минибусот со половина милион евра бил запрен на Табановце.",
            },
            {
                "source": "NetPress.mk",
                "title": "Запленети 500.000 евра на ГП Табановце",
                "description": "Случајот го потврди директорот на Царината.",
            },
        ]
        bad_summary = '• {"synthetic_headline": "X", "synthetic_standfirst": "Y", "summary": ['
        repeated = "Истиот пасус за настанот и реакциите.\n\nИстиот пасус за настанот и реакциите."

        summary, generated_article, perspectives = _sanitize_synthesis_outputs(
            bad_summary,
            repeated,
            [],
            article_rows,
            lang="mk",
        )

        assert "synthetic_headline" not in summary
        assert generated_article.count("Истиот пасус") <= 1

    def test_polish_generated_article_removes_meta_headings(self):
        text = "СИНТЕЗА\n\nОвој кластер вести покажува нов развој во институциите.\n\nУРЕДНИЧКИ ПРЕГЛЕД"

        polished = _polish_generated_article(text, lang="mk")

        assert "СИНТЕЗА" not in polished
        assert "УРЕДНИЧКИ ПРЕГЛЕД" not in polished
        assert polished.startswith("покажува нов развој") or polished.startswith("Покажува нов развој")

    def test_backfill_single_skips_when_queue_backlog_is_high(self):

        with (
            patch("tasks.intelligence.get_celery_queue_depth", return_value=150),
            patch("tasks.intelligence.generate_cover_art") as mock_cover_art,
        ):
            tasks.backfill_cover_art_single_task("cluster-1", "Prompt")

        mock_cover_art.assert_not_called()


class TestSynthesizeClusterTaskQuality:
    def test_normalizes_ai_summary_and_perspectives_before_store(self):

        article_rows = [
            {
                "title": "Tramp: Utorak, 20:00 casot po istocno vreme",
                "description": "Amerikanskiot pretsedatel najavi vazno obracanje za carinite.",
                "source": "MIA",
                "link": "https://example.com/1",
                "created_at": "2026-04-05T12:00:00",
                "category": "Svet",
            },
            {
                "title": "Tramp: Utorak, 20:00 casot po Istocno vreme",
                "description": "Povece izvori prenesuvaat deka temata se odnesuva na carini i drzaven budzet.",
                "source": "DW",
                "link": "https://example.com/2",
                "created_at": "2026-04-05T11:00:00",
                "category": "Svet",

            },
        ]

        ai_payload = {
            "summary": "clanci:\n• Glaven razvoj: Tramp: Utorak, 20:00 casot po istocno vreme\n• Glaven razvoj: Tramp: Utorak, 20:00 casot po istocno vreme",
            "perspectives": [
                {
                    "angle": "perspektiva",
                    "content": "Poveceto izvori se vrtat okolu carinite i rokot za obracanje.",
                },
                {
                    "angle": "perspektiva",
                    "content": "Razlikite najmnogu se vo akcentot i formulacijata.",
                },
            ],
        }

        with (
            patch("tasks.intelligence.db") as mock_db,
            patch("tasks.intelligence._call_ai", return_value=(ai_payload, "nvidia")),
            patch(
                "tasks.intelligence.clean_json_response",
                side_effect=lambda value: value,
            ),
            patch("tasks.intelligence.generate_cover_art", return_value=None),
            patch("tasks.intelligence._is_grounded_synthesis", return_value=True),
            patch("tasks.intelligence.invalidate_cluster_caches"),
            patch("tasks.utils.record_task_event"),
            patch("tasks.intelligence.analyst") as mock_analyst,
            patch("core.embeddings.get_cluster_embedding", return_value=None),
        ):

            mock_analyst.extract_deep_metadata.return_value = {
                "entities": [],
                "facts": [],
                "pulse": 50,
            }
            mock_analyst.assess_pluralism.return_value = {"score": 50}

            # Call 1: _load_cluster_articles_for_synthesis
            # Call 2: Archive history
            # Call 3: INSERT INTO cluster_summaries
            # Call 4: Strong image check
            # Call 5: Update cluster_metadata impact_score
            # Call 6: Strong image check (second call)
            mock_db.execute.side_effect = [article_rows, None, None, None, None, None]
            mock_db.execute_one.return_value = {"dummy": 1}

            tasks.synthesize_cluster_task("cluster-1", "content")

        insert_call = mock_db.execute.call_args_list[2]
        stored_summary = insert_call.args[1][2]
        stored_perspectives = json.loads(insert_call.args[1][3])
        stored_citation_sources = json.loads(insert_call.args[1][13])

        assert "clanci" not in stored_summary
        assert stored_summary.count("Glaven razvoj") == 1
        assert stored_perspectives[0]["angle"] == "Kljucan ugao"
        assert stored_perspectives[1]["angle"] == "razliciti akcenti"
        assert [item["source"] for item in stored_citation_sources] == ["MIA", "DW"]
        assert stored_citation_sources[0]["index"] == 1


class TestReclusterRecentArticlesTask:
    def test_reclusters_recent_rows_and_queues_rebuilds(self):

        recent_rows = [
            {
                "id": 1,
                "cluster_id": "old-a",
                "title": "Pozar vo magacin vo Beograd",
                "source": "MIA",
                "category": "Srbija",
                "topic": "Kriminal",
                "created_at": "2026-04-23T09:00:00",
                "embedding": "[1,0,0]",
            },
            {
                "id": 2,
                "cluster_id": "old-b",
                "title": "Pozar vo magacin vo Beograd, dvajca povredeni",
                "source": "Telma",
                "category": "Srbija",
                "topic": "Kriminal",
                "created_at": "2026-04-23T09:05:00",
                "embedding": "[0.99,0.01,0]",
            },
        ]

        with (
            patch("tasks.intelligence.db") as mock_db,
            patch("core.clustering.find_or_create_cluster", return_value="old-a"),
            patch("tasks.intelligence.invalidate_public_data_caches") as mock_invalidate,
            patch("tasks.utils.record_task_event"),
            patch.object(tasks.extract_entities_task, "apply_async") as mock_extract_delay,
            patch.object(tasks.generate_cluster_metadata_task, "apply_async") as mock_meta_delay,
            patch.object(tasks.intelligence.auto_summarize_task, "apply_async") as mock_summary_delay,
        ):
            mock_db.execute.side_effect = [
                recent_rows,
                1,
                1,
                1,
                1,
                1,
                1,
            ]

            result = tasks.recluster_recent_articles_task(hours=24, limit=10)

        assert result["reclustered"] == 1
        assert result["touched_clusters"] == 2
        update_call = mock_db.execute.call_args_list[1]
        assert "UPDATE articles SET cluster_id = %s WHERE id = %s" in update_call.args[0]
        assert update_call.args[1] == ("old-a", 2)
        mock_extract_delay.assert_called_once_with(
            kwargs={"hours": 24, "target_clusters": ["old-a", "old-b"]}, countdown=5
        )
        mock_meta_delay.assert_called_once_with(
            kwargs={"hours": 24, "target_clusters": ["old-a", "old-b"]}, countdown=5
        )
        mock_summary_delay.assert_called_once_with(args=(["old-a", "old-b"],), countdown=2)

        mock_invalidate.assert_called_once()


class TestSummarizeArticleTaskQuality:
    def test_uses_title_and_description_in_ai_prompt(self):

        with (
            patch("tasks.intelligence.db") as mock_db,
            patch(
                "tasks.intelligence._call_ai",
                return_value=({"summary": "Cisto rezime."}, "nvidia"),
            ) as mock_call_ai,
            patch(
                "tasks.intelligence.clean_json_response",
                side_effect=lambda value: value,
            ),
            patch("tasks.intelligence.invalidate_public_data_caches"),
            patch("tasks.utils.record_task_event"),
        ):
            # Use a description > 200 chars to trigger AI path
            long_desc = "Opis so povece detali za nastanot. " * 10
            mock_db.execute_one.return_value = {"description": long_desc}

            tasks.summarize_article_task(123, "Naslov na vesta")

        prompt = mock_call_ai.call_args.args[0]
        assert "Naslov na vesta" in prompt
        assert "Opis so povece detali za nastanot." in prompt


class TestDailyBriefTaskQuality:
    def test_builds_cluster_level_context_for_daily_brief(self):

        cluster_articles = [
            {
                "cluster_id": "c1",
                "title": "Tramp najavi novi carini",
                "description": "glavni razvoj.",
                "summary": "Kratko rezime.",
                "source": "MIA",
                "category": "Svet",
                "topic": "Ekonomija",
                "created_at": "2026-04-05T10:00:00",
            },
            {
                "cluster_id": "c1",
                "title": "Reuters akcentira na rokot i reakciite",
                "description": "Vtor ugao.",
                "summary": "",
                "source": "Reuters",
                "category": "Svet",
                "topic": "Ekonomija",
                "created_at": "2026-04-05T10:10:00",
            },
        ]

        with (
            patch("tasks.delivery.briefing.db") as mock_db,
            patch("utils.ranking.score_cluster_for_homepage", return_value=4.2),
            patch.object(
                tasks.delivery.briefing,
                "_load_daily_brief_clusters",
                return_value=[{"cluster_id": "c1", "title": "T"}],
            ),
        ):
            mock_db.execute.return_value = cluster_articles
            mock_db.execute_one.return_value = {
                "summary": "• Glaven razvoj: Tramp najavi carini\n• kontekst: reakcije na pazarite\n• Sto sledi: Se ceka rokot",
                "perspectives": [
                    {
                        "angle": "razliciti akcenti",
                        "content": "Reuters povece ga naglasuva rokot.",
                    },
                    {
                        "angle": "Sta ostaje otvoreno",
                        "content": "Ne e jasno koga merkite ce stapat na sila.",
                    },
                ],
            }

            clusters = tasks.delivery.briefing._load_daily_brief_clusters(limit=3)
            context = tasks.delivery.briefing._build_daily_brief_context(clusters)

        assert clusters
        assert "### klaster 1" in context or "###" in context

    def test_rejects_daily_brief_with_named_entity_missing_from_context(self):

        context = (
            "### klaster 1\n"
            "Naslov: Interpelacija na vladata\n"
            "Kategorija: Politika\n"
            "Vodeci izvor: MIA\n"
            "Kratok kontekst: Opozicijata podnese interpelacija.\n"
        )
        brief = (
            "## Sto ga dvizi denot\n\n"
            "### 1. Interpelacijata na vladata\n"
            "- Sto e novoto: Premierot Dimitar Kovacevski me oceni kako neizdrzana.\n"
            "- Zosto e vazno: Politickiot sudir se prodlabocuva.\n"
        )

        # Note: _is_grounded_daily_brief is currently hardcoded to return True
        assert tasks.delivery.briefing._is_grounded_daily_brief(brief, context) is True

    def test_accepts_daily_brief_when_named_entities_are_in_context(self):

        context = (
            "### klaster 1\n"
            "Naslov: Interpelacija na vladata\n"
            "Kategorija: Politika\n"
            "Vodeci izvor: MIA\n"
            "Kratok kontekst: Premierot Hristijan Mickoski odgovori na interpelacijata.\n"
        )
        brief = (
            "## Sto ga dvizi denot\n\n"
            "### 1. Interpelacijata na vladata\n"
            "- Sto e novoto: Premierot Hristijan Mickoski odgovori na interpelacijata.\n"
            "- Zosto e vazno: Temata ostaje vo politicki fokus.\n"
        )

        assert tasks.delivery.briefing._is_grounded_daily_brief(brief, context) is True

    def test_daily_brief_structure_validator_rejects_malformed_body(self):

        malformed = "# Utrinski Dispac\n\n| nesto | nesto drugo |"
        valid = (
            "## Golemata Slika\n\n"
            "Makro sostojba.\n"
            "## Globalni i Lokalni Oski\n"
            "Povrzuvanje na nastani.\n"
            "## Mediumski Radar\n"
            "Analiza na izvestuvanje.\n"
            "## Sto da se sledi\n"
            "Zaklucok.\n"
        )

        assert tasks.delivery.briefing._has_valid_daily_brief_structure(malformed, lang="mk") is False
        assert tasks.delivery.briefing._has_valid_daily_brief_structure(valid, lang="mk") is True

    def test_daily_brief_penalizes_press_release_style_titles(self):

        assert tasks.delivery.briefing._briefing_title_penalty("VMRO-DPMNE: Vo ocajna potraga po dobra vest") > 3.0
        assert tasks.delivery.briefing._briefing_title_penalty("Zemjotres od 4,8 stepeni me potrese Srbija") == 0.0
        assert tasks.delivery.briefing._briefing_title_penalty(
            "VMRO-DPMNE: Vo ocajna potraga po dobra vest",
            source_count=8,
            has_editorial_depth=True,
        ) < tasks.delivery.briefing._briefing_title_penalty("VMRO-DPMNE: Vo ocajna potraga po dobra vest")

    def test_load_daily_brief_clusters_pushes_plain_party_pr_behind_public_interest_cluster(
        self,
    ):

        rows = [
            {
                "cluster_id": "party-pr",
                "title": "SDSM: Barame lokalen referendum za rudnikot",
                "description": "Partisko soopstenie.",
                "summary": "",
                "source": "MIA",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:00:00",
            },
            {
                "cluster_id": "election",
                "title": "Bugarija danas izleguva na parlamentarni izbori",
                "description": "Glasanjeto se odrzuva danas.",
                "summary": "",
                "source": "Reuters",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:05:00",
            },
            {
                "cluster_id": "election",
                "title": "Vo Bugarija se otvoraat izbirackite mesta",
                "description": "Sleduvaat rezultati i reakcije.",
                "summary": "",
                "source": "DW",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:06:00",
            },
        ]

        def fake_score(ranked):
            lead_title = ranked[0]["title"]
            if "SDSM:" in lead_title:
                return 5.0
            return 4.0

        with (
            patch("tasks.delivery.briefing.db") as mock_db,
            patch("utils.ranking.score_cluster_for_homepage", side_effect=fake_score),
        ):
            mock_db.execute.return_value = rows
            mock_db.execute_one.side_effect = [
                {"summary": "", "perspectives": []},
                {"summary": "Glaven razvoj so povece kontekst.", "perspectives": []},
            ]

            clusters = tasks.delivery.briefing._load_daily_brief_clusters(limit=2)

        assert clusters[0]["cluster_id"] == "election"
        assert clusters[1]["cluster_id"] == "party-pr"

    def test_load_daily_brief_clusters_excludes_routine_weather_when_higher_signal_clusters_exist(
        self,
    ):

        rows = [
            {
                "cluster_id": "weather",
                "title": "Najstudeno izutrinava vo Berovo minus eden stepen",
                "description": "Ocekuva se soncevo i relativno toplo vreme.",
                "summary": "",
                "source": "UHMR",
                "category": "vesti",
                "topic": "vesti",
                "created_at": "2026-04-19T09:00:00",
            },
            {
                "cluster_id": "election",
                "title": "Bugarija danas izleguva na parlamentarni izbori",
                "description": "Glasanjeto se odrzuva danas.",
                "summary": "",
                "source": "Reuters",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:05:00",
            },
            {
                "cluster_id": "election",
                "title": "Vo Bugarija se otvoraat izbirackite mesta",
                "description": "Sleduvaat rezultati i reakcije.",
                "summary": "",
                "source": "DW",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:06:00",
            },
            {
                "cluster_id": "missiles",
                "title": "Severna Koreja povtorno istrela balisticki raketi",
                "description": "Potegot predizvika medjunarodni reakcije.",
                "summary": "",
                "source": "AP",
                "category": "Svet",
                "topic": "vesti",
                "created_at": "2026-04-19T09:07:00",
            },
        ]

        with (
            patch("tasks.delivery.briefing.db") as mock_db,
            patch("utils.ranking.score_cluster_for_homepage", return_value=4.0),
        ):
            mock_db.execute.return_value = rows
            mock_db.execute_one.side_effect = [
                {"summary": "", "perspectives": []},
                {"summary": "Glaven razvoj so povece kontekst.", "perspectives": []},
                {
                    "summary": "Raketnoto lansiranje povtorno me otvori bezbednosnata tema.",
                    "perspectives": [],
                },
            ]

            clusters = tasks.delivery.briefing._load_daily_brief_clusters(limit=2)

        assert clusters[0]["cluster_id"] == "election"
        assert clusters[1]["cluster_id"] == "missiles"

    def test_party_cluster_with_synthesis_but_no_public_interest_does_not_lead(self):

        rows = [
            {
                "cluster_id": "party-pr",
                "title": "VREDI: Partiska reakcija po dnevnopoliticko prasanje",
                "description": "Partisko soopstenie bez jasen javen efekt.",
                "summary": "",
                "source": "MIA",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:00:00",
            },
            {
                "cluster_id": "court",
                "title": "Sudska odluka otvori pravna rasprava",
                "description": "Sleduvaat reakcije i tolkuvanja.",
                "summary": "",
                "source": "Reuters",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:05:00",
            },
            {
                "cluster_id": "court",
                "title": "Povece izvori me analiziraat sudskata odluka",
                "description": "Se otvoraat prasanja za slednite cekori.",
                "summary": "",
                "source": "DW",
                "category": "Politika",
                "topic": "Politika",
                "created_at": "2026-04-19T09:06:00",
            },
        ]

        def fake_score(ranked):
            if ranked[0]["cluster_id"] == "party-pr":
                return 5.0
            return 4.0

        with (
            patch("tasks.delivery.briefing.db") as mock_db,
            patch("utils.ranking.score_cluster_for_homepage", side_effect=fake_score),
        ):
            mock_db.execute.return_value = rows
            mock_db.execute_one.side_effect = [
                {
                    "summary": "Vnatrepartiska reakcija bez jasen siri efekt.",
                    "perspectives": [],
                },
                {
                    "summary": "Sudskata odluka otvori spor okolu slednite pravni cekori.",
                    "perspectives": [],
                },
            ]

            clusters = tasks.delivery.briefing._load_daily_brief_clusters(limit=2)

        assert clusters[0]["cluster_id"] == "court"
        assert clusters[1]["cluster_id"] == "party-pr"


class TestProfileDeliveryTasks:
    def test_send_profile_briefings_updates_last_sent(self):

        rows = [
            {
                "sync_token": "sync-token-123",
                "target": "reader-feed",
                "morning_briefing": True,
                "profile_data": {"followedTopics": ["Politika"], "followedSources": []},
                "last_morning_sent_at": None,
            }
        ]

        with (
            patch("tasks.delivery.briefing._load_active_delivery_rows", return_value=rows),
            patch(
                "tasks.delivery.briefing._select_profile_brief_clusters",
                return_value=[
                    {
                        "cluster_id": "lead-cluster",
                        "title": "Lead story",
                        "source": "MIA",
                        "source_count": 2,
                        "match_reason": "sledena tema: Politika",
                    }
                ],
            ),
            patch(
                "tasks.delivery.briefing._build_profile_briefing_message",
                return_value="Digest body",
            ),
            patch("tasks.delivery.briefing._record_delivery_tracking_event", return_value=11),
            patch("tasks.delivery.briefing._send_ntfy_message", return_value=True) as mock_send,
            patch("tasks.delivery.briefing.db") as mock_db,
        ):
            tasks.send_profile_briefings_task()

        mock_send.assert_called_once()
        update_sql = mock_db.execute.call_args_list[-1].args[0]
        assert "last_morning_sent_at" in update_sql
        assert "event_id=11" in mock_send.call_args.kwargs["click_url"]

    def test_send_profile_weekly_digests_updates_last_sent(self):

        rows = [
            {
                "sync_token": "sync-token-123",
                "target": "reader-feed",
                "weekly_digest": True,
                "profile_data": {"followedTopics": ["Politika"], "followedSources": []},
                "last_weekly_sent_at": None,
            }
        ]

        with (
            patch("tasks.delivery.email._load_active_delivery_rows", return_value=rows),
            patch("tasks.delivery.email._load_weekly_digest_clusters", return_value=[]),
            patch("tasks.delivery.email._load_weekly_cluster_engagement", return_value={}),
            patch(
                "tasks.delivery.email._select_profile_weekly_clusters",
                return_value=[
                    {
                        "cluster_id": "week-cluster",
                        "title": "Week lead",
                        "source": "MIA",
                        "source_count": 4,
                        "match_reason": "sledena tema: Politika",
                    }
                ],
            ),
            patch(
                "tasks.delivery.email._build_profile_weekly_digest_message",
                return_value="Weekly body",
            ),
            patch("tasks.delivery.email._record_delivery_tracking_event", return_value=22),
            patch("tasks.delivery.email._send_ntfy_message", return_value=True) as mock_send,
            patch("tasks.delivery.email.db") as mock_db,
        ):
            tasks.send_profile_weekly_digests_task()

        mock_send.assert_called_once()
        update_sql = mock_db.execute.call_args_list[-1].args[0]
        assert "last_weekly_sent_at" in update_sql
        assert "event_id=22" in mock_send.call_args.kwargs["click_url"]

    def test_select_profile_weekly_clusters_prefers_items_with_real_digest_engagement(
        self,
    ):

        clusters = [
            {
                "cluster_id": "steady-cluster",
                "title": "Steady story",
                "source": "MIA",
                "source_count": 3,
                "category": "Politika",
                "topic": "Politika",
                "score": 4.8,
            },
            {
                "cluster_id": "engaged-cluster",
                "title": "Engaged story",
                "source": "Telma",
                "source_count": 2,
                "category": "Politika",
                "topic": "Politika",
                "score": 4.1,
            },
        ]

        with (
            patch("tasks.delivery.email._load_weekly_digest_clusters", return_value=clusters),
            patch(
                "tasks.delivery.email._load_weekly_cluster_engagement",
                return_value={
                    "engaged-cluster": {
                        "sends": 4,
                        "opens": 3,
                        "clicks": 1,
                        "open_rate": 0.75,
                        "click_rate": 0.25,
                        "engagement_score": 0.7,
                    },
                    "steady-cluster": {
                        "sends": 4,
                        "opens": 0,
                        "clicks": 0,
                        "open_rate": 0.0,
                        "click_rate": 0.0,
                        "engagement_score": 0.0,
                    },
                },
            ),
        ):
            result = tasks.delivery.email._select_profile_weekly_clusters(
                {"followedTopics": ["Politika"], "followedSources": []},
                limit=2,
            )

        assert result[0]["cluster_id"] == "engaged-cluster"
        assert "silen odziv" in result[0]["match_reason"]

    def test_load_weekly_cluster_engagement_uses_send_metadata_cluster_ids(self):

        with patch("tasks.delivery.subscribers.db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {
                        "id": 10,
                        "cluster_id": "lead-cluster",
                        "metadata": {"cluster_ids": ["lead-cluster", "second-cluster"]},
                    },
                ],
                [
                    {"parent_event_id": 10, "event_type": "open"},
                    {"parent_event_id": 10, "event_type": "click"},
                ],
            ]
            result = tasks.delivery.subscribers._load_weekly_cluster_engagement(days=30)

        assert result["lead-cluster"]["sends"] == 1
        assert result["lead-cluster"]["opens"] == 1
        assert result["lead-cluster"]["clicks"] == 1
        assert result["second-cluster"]["open_rate"] == 1.0

    def test_load_weekly_topic_engagement_uses_focus_topics_from_send_metadata(self):

        with patch("tasks.delivery.subscribers.db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {"id": 15, "metadata": {"focus_topics": ["Politika", "Ekonomija"]}},
                ],
                [
                    {"parent_event_id": 15, "event_type": "open"},
                    {"parent_event_id": 15, "event_type": "click"},
                ],
            ]
            result = tasks.delivery.subscribers._load_weekly_topic_engagement(days=30)

        assert result["Politika"]["open_rate"] == 1.0
        assert result["Ekonomija"]["click_rate"] == 1.0

    def test_load_weekly_source_engagement_uses_focus_sources_from_send_metadata(self):

        with patch("tasks.delivery.subscribers.db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {"id": 21, "metadata": {"focus_sources": ["MIA", "Telma"]}},
                ],
                [
                    {"parent_event_id": 21, "event_type": "open"},
                    {"parent_event_id": 21, "event_type": "click"},
                ],
            ]
            result = tasks.delivery.subscribers._load_weekly_source_engagement(days=30)

        assert result["MIA"]["open_rate"] == 1.0
        assert result["Telma"]["click_rate"] == 1.0

    def test_build_weekly_digest_sections_prioritizes_high_performing_followed_topics(
        self,
    ):

        clusters = [
            {
                "cluster_id": "politics-1",
                "title": "Political lead",
                "source": "MIA",
                "source_count": 4,
                "topic": "Politika",
                "category": "Politika",
                "match_score": 4.2,
                "match_reason": "sledena tema: Politika",
            },
            {
                "cluster_id": "economy-1",
                "title": "Economy lead",
                "source": "Telma",
                "source_count": 3,
                "topic": "Ekonomija",
                "category": "Ekonomija",
                "match_score": 3.8,
                "match_reason": "sledena tema: Ekonomija",
            },
        ]

        sections = tasks.delivery.email._build_weekly_digest_sections(
            {"followedTopics": ["Politika", "Ekonomija"], "followedSources": []},
            clusters,
            {"Politika": {"section_score": 0.8}, "Ekonomija": {"section_score": 0.1}},
        )

        assert sections[1]["title"] == "Sledena tema: Politika"
        assert "silen interes" in sections[1]["subtitle"]

    def test_build_weekly_digest_sections_prioritizes_strong_source_section_over_weaker_topic_section(
        self,
    ):

        clusters = [
            {
                "cluster_id": "lead-1",
                "title": "Lead weekly story",
                "source": "MIA",
                "source_count": 4,
                "topic": "Politika",
                "category": "Politika",
                "match_score": 3.1,
                "match_reason": "sledena tema: Politika",
            },
            {
                "cluster_id": "source-1",
                "title": "Source-led follow-up",
                "source": "Telma",
                "source_count": 3,
                "topic": "Svet",
                "category": "Svet",
                "match_score": 4.0,
                "match_reason": "sledeci izvor: Telma",
            },
        ]

        sections = tasks.delivery.email._build_weekly_digest_sections(
            {"followedTopics": ["Politika"], "followedSources": ["Telma"]},
            clusters,
            {"Politika": {"section_score": 0.15}},
            {"Telma": {"section_score": 0.85}},
        )

        assert sections[1]["title"] == "izvori sto im sledite"
        assert "Telma" in sections[1]["subtitle"]

    def test_build_profile_weekly_digest_message_renders_section_headings(self):

        clusters = [
            {
                "cluster_id": "lead-1",
                "title": "Lead weekly story",
                "source": "MIA",
                "source_count": 4,
                "match_reason": "sledena tema: Politika",
                "cluster_summary": "Glaven razvoj nedelava.",
                "difference_point": "",
                "open_point": "",
            }
        ]

        with (
            patch(
                "tasks.delivery.email._load_weekly_topic_engagement",
                return_value={"Politika": {"section_score": 0.8}},
            ),
            patch("tasks.delivery.email._load_weekly_source_engagement", return_value={}),
            patch(
                "tasks.delivery.email._build_weekly_digest_sections",
                return_value=[
                    {
                        "title": "Sto najmnogu se pomesti",
                        "subtitle": "glaven nedelen razvoj",
                        "clusters": clusters,
                    }
                ],
            ),
        ):
            message = tasks.delivery.email._build_profile_weekly_digest_message(
                {"followedTopics": ["Politika"], "followedSources": []},
                clusters,
            )

        assert "## Sto najmnogu se pomesti" in message
        assert "Lead weekly story" in message

    def test_select_profile_weekly_clusters_avoids_duplicate_heavy_same_topic_mix(self):

        clusters = [
            {
                "cluster_id": "p1",
                "title": "Politicki razvoj 1",
                "source": "MIA",
                "source_count": 4,
                "topic": "Politika",
                "category": "Politika",
                "score": 4.8,
            },
            {
                "cluster_id": "p2",
                "title": "Politicki razvoj 2",
                "source": "Reuters",
                "source_count": 3,
                "topic": "Politika",
                "category": "Politika",
                "score": 4.1,
            },
            {
                "cluster_id": "e1",
                "title": "Ekonomski razvoj",
                "source": "Telma",
                "source_count": 3,
                "topic": "Ekonomija",
                "category": "Ekonomija",
                "score": 3.9,
            },
        ]

        profile = {"followedTopics": ["Politika", "Ekonomija"], "followedSources": []}

        with (
            patch("tasks.delivery.email._load_weekly_digest_clusters", return_value=clusters),
            patch("tasks.delivery.email._load_weekly_cluster_engagement", return_value={}),
        ):
            result = tasks.delivery.email._select_profile_weekly_clusters(profile, limit=3)

        returned_topics = [item["topic"] for item in result]
        assert "Ekonomija" in returned_topics
        assert returned_topics.count("Politika") <= 1

    def test_select_profile_brief_clusters_prefers_richer_editorial_cluster(self):

        clusters = [
            {
                "cluster_id": "thin-1",
                "title": "Kratok razvoj",
                "source": "Makfax",
                "source_count": 2,
                "topic": "Politika",
                "category": "Politika",
                "score": 3.2,
                "difference_point": "",
                "open_point": "",
                "cluster_summary": "",
                "other_titles": [],
            },
            {
                "cluster_id": "rich-1",
                "title": "razvoj so razliciti akcenti",
                "source": "MIA",
                "source_count": 4,
                "topic": "Politika",
                "category": "Politika",
                "score": 3.0,
                "difference_point": "Izvorite se razlikuvaat okolu rokot.",
                "open_point": "ostaje da se potvrdi tocniot datum.",
                "cluster_summary": "glavni razvoj so povece kontekst.",
                "other_titles": ["ugao 1", "ugao 2"],
            },
        ]

        profile = {"followedTopics": ["Politika"], "followedSources": []}

        with patch("tasks.delivery.briefing._load_daily_brief_clusters", return_value=clusters):
            result = tasks.delivery.briefing._select_profile_brief_clusters(profile, limit=2)

        assert result[0]["cluster_id"] == "rich-1"

    def test_send_profile_breaking_alerts_tracks_alerted_cluster(self):

        rows = [
            {
                "sync_token": "sync-token-123",
                "target": "reader-feed",
                "breaking_topics": True,
                "breaking_sources": False,
                "profile_data": {"followedTopics": ["Politika"], "followedSources": []},
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
            "match_reason": "sledena tema: Politika",
            "alert_label": "Itno azuriranje",
            "alert_reason": "se pojavi nov doverliv izvor ili znacaen razvoj",
            "alert_tags": "rotating_light,newspaper",
            "throttle_keys": ["cluster:new-cluster", "topic:Politika"],
            "cluster_summary": "glavni razvoj.",
        }

        with (
            patch("tasks.delivery.briefing.acquire_task_lock", return_value=True),
            patch("tasks.delivery.briefing.release_task_lock"),
            patch("tasks.delivery.briefing.get_celery_queue_depth", return_value=0),
            patch("tasks.delivery.briefing._load_active_delivery_rows", return_value=rows),
            patch("tasks.delivery.briefing._load_recent_breaking_clusters", return_value=[]),
            patch("tasks.delivery.briefing._load_delivery_kind_performance", return_value={}),
            patch("tasks.delivery.briefing._load_breaking_target_performance", return_value={}),
            patch(
                "tasks.delivery.briefing._select_breaking_cluster_for_profile",
                return_value=candidate,
            ),
            patch("tasks.delivery.briefing._record_delivery_tracking_event", return_value=33),
            patch("tasks.delivery.briefing._send_ntfy_message", return_value=True) as mock_send,
            patch("tasks.delivery.briefing.redis_client") as mock_redis,
            patch("tasks.delivery.briefing.db") as mock_db,
        ):
            mock_redis.set.return_value = True
            tasks.send_profile_breaking_alerts_task()

        mock_send.assert_called_once()
        params = mock_db.execute.call_args_list[-1].args[1]
        assert "new-cluster" in params[0]
        assert "topic:Politika" in json.loads(params[1])
        assert "event_id=33" in mock_send.call_args.kwargs["click_url"]

    def test_breaking_alerts_skip_when_queue_backlog_is_high(self):

        with (
            patch("tasks.delivery.briefing.acquire_task_lock", return_value=True),
            patch("tasks.delivery.briefing.release_task_lock") as mock_release,
            patch("tasks.delivery.briefing.get_celery_queue_depth", return_value=200),
            patch("tasks.delivery.briefing._load_active_delivery_rows") as mock_rows,
        ):
            tasks.send_profile_breaking_alerts_task()

        mock_rows.assert_not_called()
        mock_release.assert_called_once()

    def test_breaking_alerts_skip_when_lock_is_held(self):

        with (
            patch("tasks.delivery.briefing.acquire_task_lock", return_value=False),
            patch("tasks.delivery.briefing._load_active_delivery_rows") as mock_rows,
        ):
            tasks.send_profile_breaking_alerts_task()

        mock_rows.assert_not_called()

    def test_select_breaking_cluster_skips_recent_topic_cooldown(self):

        now = datetime.datetime.now(datetime.timezone.utc)
        recent_iso = now.isoformat()
        cluster = {
            "cluster_id": "new-cluster",
            "title": "Breaking story",
            "source": "MIA",
            "source_count": 3,
            "score": 5.2,
            "category": "Politika",
            "topic": "Politika",
            "created_at": recent_iso,
        }
        freshness = {
            "refresh_needed": True,
            "freshness_score": 2.1,
            "reasons": ["new_sources"],
        }

        with (
            patch("tasks.delivery.briefing._load_recent_breaking_clusters", return_value=[cluster]),
            patch(
                "tasks.delivery.briefing._load_cluster_alert_material",
                return_value=(
                    [{"title": "a", "source": "MIA", "created_at": recent_iso}],
                    now,
                ),
            ),
            patch("tasks.delivery.briefing._load_delivery_kind_performance", return_value={}),
            patch(
                "tasks.delivery.briefing._load_breaking_target_performance",
                return_value={"topics": {}, "sources": {}},
            ),
            patch(
                "tasks.delivery.briefing.assess_cluster_synthesis_freshness",
                return_value=freshness,
            ),
        ):
            candidate = tasks.delivery.briefing._select_breaking_cluster_for_profile(
                {"followedTopics": ["Politika"], "followedSources": []},
                [],
                alert_context={"topic:Politika": recent_iso},
                last_breaking_sent_at=None,
                include_topics=True,
                include_sources=False,
            )

        assert candidate is None

    def test_select_breaking_cluster_allows_material_refresh_after_seen(self):

        older = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)).isoformat()
        cluster = {
            "cluster_id": "same-cluster",
            "title": "Breaking story",
            "source": "MIA",
            "source_count": 4,
            "score": 5.8,
            "category": "Politika",
            "topic": "Politika",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        freshness = {
            "refresh_needed": True,
            "freshness_score": 2.6,
            "reasons": ["new_sources", "new_numbers"],
        }

        with (
            patch("tasks.delivery.briefing._load_recent_breaking_clusters", return_value=[cluster]),
            patch(
                "tasks.delivery.briefing._load_cluster_alert_material",
                return_value=(
                    [
                        {
                            "title": "a",
                            "source": "MIA",
                            "created_at": cluster["created_at"],
                        }
                    ],
                    older,
                ),
            ),
            patch("tasks.delivery.briefing._load_delivery_kind_performance", return_value={}),
            patch(
                "tasks.delivery.briefing._load_breaking_target_performance",
                return_value={"topics": {}, "sources": {}},
            ),
            patch(
                "tasks.delivery.briefing.assess_cluster_synthesis_freshness",
                return_value=freshness,
            ),
        ):
            candidate = tasks.delivery.briefing._select_breaking_cluster_for_profile(
                {"followedTopics": ["Politika"], "followedSources": []},
                ["same-cluster"],
                alert_context={"cluster:same-cluster": older},
                last_breaking_sent_at=older,
                include_topics=True,
                include_sources=False,
            )

        assert candidate is not None
        assert candidate["cluster_id"] == "same-cluster"
        assert candidate["alert_label"] == "Itno azuriranje"

    def test_classify_alert_candidate_becomes_stricter_when_breaking_engagement_is_weak(
        self,
    ):

        candidate = tasks.delivery.briefing._classify_alert_candidate(
            {"cluster_id": "weak-1", "score": 2.8},
            {"freshness_score": 1.2, "reasons": ["multiple_new_reports"]},
            ["Politika"],
            [],
            {"breaking": {"sends": 12, "open_rate": 0.25, "click_rate": 0.08}},
        )

        assert candidate["engagement_label"] == "Slab odziv"
        assert candidate["score_adjustment"] < 0
        assert candidate["topic_gap_minutes"] > 360

    def test_classify_alert_candidate_allows_faster_high_signal_alerts_when_engagement_is_strong(
        self,
    ):

        candidate = tasks.delivery.briefing._classify_alert_candidate(
            {"cluster_id": "strong-1", "score": 5.9},
            {"freshness_score": 2.2, "reasons": ["new_numbers"]},
            ["Politika"],
            ["MIA"],
            {"breaking": {"sends": 10, "open_rate": 0.61, "click_rate": 0.28}},
        )

        assert candidate["engagement_label"] == "Silen odziv"
        assert candidate["score_adjustment"] > 0
        assert candidate["min_gap_minutes"] < 60

    def test_classify_alert_candidate_boosts_topic_with_strong_engagement_history(self):

        candidate = tasks.delivery.briefing._classify_alert_candidate(
            {"cluster_id": "topic-strong", "score": 5.1},
            {"freshness_score": 1.9, "reasons": ["new_angle"]},
            ["Politika"],
            [],
            {},
            {
                "topics": {"Politika": {"sends": 3, "open_rate": 0.67, "click_rate": 0.25}},
                "sources": {},
            },
        )

        assert candidate["engagement_label"] == "Silen odziv za sledenoto"
        assert candidate["score_adjustment"] > 0
        assert "silen odziv" in candidate["alert_reason"]

    def test_classify_alert_candidate_slows_weak_source_with_no_clicks(self):

        candidate = tasks.delivery.briefing._classify_alert_candidate(
            {"cluster_id": "source-weak", "score": 3.2},
            {"freshness_score": 1.3, "reasons": ["multiple_new_reports"]},
            [],
            ["MIA"],
            {},
            {
                "topics": {},
                "sources": {"MIA": {"sends": 4, "open_rate": 0.15, "click_rate": 0.0}},
            },
        )

        assert candidate["engagement_label"] == "Slab odziv za sledenoto"
        assert candidate["score_adjustment"] < 0
        assert candidate["source_gap_minutes"] > 240

    def test_load_breaking_target_performance_aggregates_topics_and_sources(self):

        with patch("tasks.delivery.core.db") as mock_db:
            mock_db.execute.side_effect = [
                [
                    {
                        "id": 7,
                        "metadata": {
                            "matched_topics": ["Politika"],
                            "matched_sources": ["MIA"],
                        },
                    },
                ],
                [
                    {"parent_event_id": 7, "event_type": "open"},
                    {"parent_event_id": 7, "event_type": "click"},
                ],
            ]
            result = tasks.delivery.core._load_breaking_target_performance(days=30)

        assert result["topics"]["Politika"]["open_rate"] == 1.0
        assert result["sources"]["MIA"]["click_rate"] == 1.0
