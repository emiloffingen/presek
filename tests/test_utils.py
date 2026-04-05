import pytest
import datetime
import math
from unittest.mock import patch, MagicMock
from utils import (
    score_cluster,
    score_cluster_for_synthesis,
    score_cluster_for_homepage,
    rank_articles_in_cluster,
    get_source_effective_weight,
    assess_cluster_synthesis_freshness,
    build_cluster_source_signals,
    annotate_cluster_articles,
    get_source_trust_label,
    build_read_next_clusters,
    build_source_reputation_rows,
)


def _make_article(source="MIA", created_at=None, clicks=0):
    """Helper to build a fake article dict."""
    return {
        "source": source,
        "created_at": created_at or datetime.datetime.now(),
        "clicks": clicks,
        "cluster_id": "test-cluster",
        "title": "Test article",
    }


# ── score_cluster ─────────────────────────────────────────────────

class TestScoreCluster:
    @patch("utils.get_source_health_map", return_value={})
    def test_single_article_recent(self, _mock_health):
        arts = [_make_article()]
        s = score_cluster(arts)
        assert s > 0

    @patch("utils.get_source_health_map", return_value={})
    def test_more_sources_higher_score(self, _mock_health):
        one_source = [_make_article("MIA")]
        two_sources = [_make_article("MIA"), _make_article("Sitel")]
        assert score_cluster(two_sources) > score_cluster(one_source)

    @patch("utils.get_source_health_map", return_value={})
    def test_recency_decay(self, _mock_health):
        recent = [_make_article(created_at=datetime.datetime.now())]
        old = [_make_article(created_at=datetime.datetime.now() - datetime.timedelta(hours=24))]
        assert score_cluster(recent) > score_cluster(old)

    @patch("utils.get_source_health_map", return_value={})
    def test_click_bonus(self, _mock_health):
        no_clicks = [_make_article(clicks=0)]
        with_clicks = [_make_article(clicks=100)]
        assert score_cluster(with_clicks) > score_cluster(no_clicks)

    @patch("utils.get_source_health_map", return_value={})
    def test_credibility_matters(self, _mock_health):
        # MIA has credibility 2.0, Press24 has 0.9
        high_cred = [_make_article("MIA")]
        low_cred = [_make_article("Press24")]
        assert score_cluster(high_cred) > score_cluster(low_cred)

    @patch("utils.get_source_health_map", return_value={})
    def test_duplicate_sources_counted_once(self, _mock_health):
        """Same source appearing twice shouldn't double the credibility score."""
        two_same = [_make_article("MIA"), _make_article("MIA")]
        one = [_make_article("MIA")]
        # Breadth differs (log1p(2) vs log1p(1)), but cred_score is the same
        s_two = score_cluster(two_same)
        s_one = score_cluster(one)
        # The score difference should come only from breadth, not doubled credibility
        assert s_two > s_one  # more articles = more breadth
        # But ratio should be modest (log1p(2)/log1p(1) ≈ 1.58)
        assert s_two / s_one < 2.0

    @patch("utils.get_source_health_map", return_value={})
    def test_string_timestamp_fallback(self, _mock_health):
        """When created_at is an ISO string, it should still work."""
        arts = [_make_article()]
        arts[0]["created_at"] = datetime.datetime.now().isoformat()
        s = score_cluster(arts)
        assert s > 0

    @patch("utils.get_source_health_map", return_value={})
    def test_none_clicks_handled(self, _mock_health):
        arts = [_make_article()]
        arts[0]["clicks"] = None
        s = score_cluster(arts)
        assert s > 0

    @patch("utils.get_source_health_map", return_value={})
    def test_empty_list(self, _mock_health):
        """Empty article list should return 0 or a low score."""
        s = score_cluster([])
        assert s == 0 or s == 0.0

    @patch("utils.get_source_health_map", return_value={"MIA": {"quality_score": 0.3}})
    def test_source_health_penalizes_cluster_score(self, _mock_health):
        weak = [_make_article("MIA")]
        with patch("utils.get_source_health_map", return_value={}):
            strong_score = score_cluster(weak)
        weak_score = score_cluster(weak)
        assert weak_score < strong_score

    @patch("utils.get_source_health_map", return_value={})
    def test_synthesis_priority_prefers_richer_multi_source_cluster(self, _mock_health):
        shallow = [
            {
                **_make_article("MIA"),
                "title": "Трамп најави говор",
                "description": "",
            },
            {
                **_make_article("MIA"),
                "title": "Трамп најави говор",
                "description": "",
            },
        ]
        richer = [
            {
                **_make_article("MIA"),
                "title": "Трамп најави говор за царини",
                "description": "Опис со повеќе детали за царините.",
            },
            {
                **_make_article("Reuters"),
                "title": "Трамп ќе објави економски мерки во вторник",
                "description": "Вториот извор додава контекст и реакција.",
            },
            {
                **_make_article("DW"),
                "title": "Европските пазари реагираат на најавата на Трамп",
                "description": "Трет извор со поинаков акцент.",
            },
        ]

        assert score_cluster_for_synthesis(richer) > score_cluster_for_synthesis(shallow)

    @patch("utils.get_source_health_map", return_value={})
    def test_synthesis_priority_rewards_title_divergence(self, _mock_health):
        aligned = [
            {
                **_make_article("MIA"),
                "title": "Трамп најави говор за царини",
                "description": "Опис еден.",
            },
            {
                **_make_article("Reuters"),
                "title": "Трамп најави говор за царини",
                "description": "Опис два.",
            },
        ]
        divergent = [
            {
                **_make_article("MIA"),
                "title": "Трамп најави говор за царини",
                "description": "Опис еден.",
            },
            {
                **_make_article("Reuters"),
                "title": "Пазарите реагираат на говорот на Трамп и новите мерки",
                "description": "Опис два.",
            },
        ]

        assert score_cluster_for_synthesis(divergent) > score_cluster_for_synthesis(aligned)

    @patch("utils.get_source_health_map", return_value={})
    def test_homepage_priority_prefers_corroborated_multi_source_cluster(self, _mock_health):
        thin = [
            {
                **_make_article("Press24"),
                "title": "Трамп најави мерки",
                "description": "",
            },
            {
                **_make_article("Press24", created_at=datetime.datetime.now() - datetime.timedelta(minutes=5)),
                "title": "Трамп најави нови мерки",
                "description": "",
            },
        ]
        richer = [
            {
                **_make_article("MIA"),
                "title": "Трамп најави нови царини",
                "description": "Главен развој со детали.",
            },
            {
                **_make_article("Reuters", created_at=datetime.datetime.now() - datetime.timedelta(minutes=8)),
                "title": "Reuters пишува за реакциите и рокот за новите царини",
                "description": "Втор извор со поширок контекст.",
            },
            {
                **_make_article("DW", created_at=datetime.datetime.now() - datetime.timedelta(minutes=12)),
                "title": "Европските пазари реагираат на најавените царини",
                "description": "Трет извор со потврда и последица.",
            },
        ]

        assert score_cluster_for_homepage(richer) > score_cluster_for_homepage(thin)

    @patch("utils.get_source_health_map", return_value={})
    def test_homepage_priority_penalizes_single_source_churn(self, _mock_health):
        single_source = [
            {
                **_make_article("Press24"),
                "title": "Кратка вест за развојот",
                "description": "",
            },
            {
                **_make_article("Press24", created_at=datetime.datetime.now() - datetime.timedelta(minutes=3)),
                "title": "Уште краток follow-up за развојот",
                "description": "",
            },
        ]
        broader = [
            {
                **_make_article("Makfax"),
                "title": "Главен развој во темата",
                "description": "Опис еден.",
            },
            {
                **_make_article("MIA", created_at=datetime.datetime.now() - datetime.timedelta(minutes=6)),
                "title": "Втор извор го потврдува главниот развој",
                "description": "Опис два.",
            },
        ]

        assert score_cluster_for_homepage(broader) > score_cluster_for_homepage(single_source)


# ── rank_articles_in_cluster ──────────────────────────────────────

class TestRankArticles:
    @patch("utils.get_source_health_map", return_value={})
    def test_highest_credibility_first(self, _mock_health):
        arts = [
            _make_article("Press24"),   # 0.9
            _make_article("MIA"),       # 2.0
            _make_article("Sitel"),     # 1.7
        ]
        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "MIA"
        assert ranked[1]["source"] == "Sitel"
        assert ranked[2]["source"] == "Press24"

    @patch("utils.get_source_health_map", return_value={})
    def test_single_article(self, _mock_health):
        arts = [_make_article("MIA")]
        ranked = rank_articles_in_cluster(arts)
        assert len(ranked) == 1
        assert ranked[0]["source"] == "MIA"

    @patch("utils.get_source_health_map", return_value={})
    def test_unknown_source_gets_default(self, _mock_health):
        arts = [_make_article("Unknown"), _make_article("MIA")]
        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "MIA"  # 2.0 > 0.8 default

    @patch("utils.get_source_health_map", return_value={"MIA": {"quality_score": 0.25}})
    def test_source_health_can_reorder_articles(self, _mock_health):
        arts = [_make_article("MIA"), _make_article("Sitel")]
        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "Sitel"


class TestSourceEffectiveWeight:
    @patch("utils.get_source_health_map", return_value={"MIA": {"quality_score": 0.2}})
    def test_effective_weight_uses_health_multiplier(self, _mock_health):
        assert get_source_effective_weight("MIA") < 2.0

    @patch("utils.get_source_health_map", return_value={})
    def test_trust_label_reflects_source_weight(self, _mock_health):
        assert get_source_trust_label("MIA") == "Висока доверба"
        assert get_source_trust_label("Makfax") == "Потврден извор"
        assert get_source_trust_label("Press24") == "Следен извор"


class TestSynthesisFreshness:
    @patch("utils.get_source_health_map", return_value={})
    def test_missing_synthesis_requests_refresh(self, _mock_health):
        arts = [
            {
                **_make_article("MIA"),
                "title": "Трамп најави нови царини",
                "description": "Прв извештај со главниот развој.",
            },
            {
                **_make_article("Reuters"),
                "title": "Реакции по најавата на Трамп",
                "description": "Втор извор со контекст.",
            },
        ]

        result = assess_cluster_synthesis_freshness(arts, None)

        assert result["refresh_needed"] is True
        assert "missing_synthesis" in result["reasons"]

    @patch("utils.get_source_health_map", return_value={})
    def test_no_new_articles_keeps_synthesis_fresh(self, _mock_health):
        created_at = datetime.datetime.now() - datetime.timedelta(minutes=30)
        arts = [
            {**_make_article("MIA", created_at=created_at), "title": "Трамп најави царини", "description": "Опис."},
            {**_make_article("Reuters", created_at=created_at), "title": "Реакции на царините", "description": "Опис."},
        ]

        result = assess_cluster_synthesis_freshness(arts, created_at)

        assert result["refresh_needed"] is False
        assert result["new_article_count"] == 0

    @patch("utils.get_source_health_map", return_value={})
    def test_new_source_and_numbers_mark_cluster_stale(self, _mock_health):
        synthesis_time = datetime.datetime.now() - datetime.timedelta(hours=2)
        old_time = synthesis_time - datetime.timedelta(minutes=30)
        new_time = synthesis_time + datetime.timedelta(minutes=25)
        arts = [
            {
                **_make_article("MIA", created_at=old_time),
                "title": "Владата најави пакет од 100 милиони",
                "description": "Прв извештај за пакетот.",
            },
            {
                **_make_article("Reuters", created_at=new_time),
                "title": "Reuters пишува за 120 милиони и нов рок",
                "description": "Се додава друга бројка и нов извор.",
            },
        ]

        result = assess_cluster_synthesis_freshness(arts, synthesis_time)

        assert result["refresh_needed"] is True
        assert "new_sources" in result["reasons"]
        assert "new_numbers" in result["reasons"]

    @patch("utils.get_source_health_map", return_value={})
    def test_single_quick_followup_does_not_force_refresh_in_cooldown(self, _mock_health):
        synthesis_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
        arts = [
            {
                **_make_article("MIA", created_at=synthesis_time - datetime.timedelta(minutes=5)),
                "title": "Трамп најави царини",
                "description": "Прв извештај.",
            },
            {
                **_make_article("MIA", created_at=synthesis_time + datetime.timedelta(minutes=4)),
                "title": "Трамп најави царини за увоз",
                "description": "Мало дополнување без нов извор.",
            },
        ]

        result = assess_cluster_synthesis_freshness(arts, synthesis_time)

        assert result["refresh_needed"] is False


class TestSourceSignals:
    @patch("utils.get_source_health_map", return_value={})
    def test_build_cluster_source_signals_marks_lead_and_trust(self, _mock_health):
        now = datetime.datetime.now()
        arts = [
            {
                **_make_article("MIA", created_at=now - datetime.timedelta(minutes=30)),
                "title": "Трамп најави царини",
                "description": "Прв извештај.",
            },
            {
                **_make_article("Reuters", created_at=now - datetime.timedelta(minutes=20)),
                "title": "Реакции на царините и новите мерки на Трамп",
                "description": "Вториот извор носи дополнителен контекст.",
            },
            {
                **_make_article("Press24", created_at=now - datetime.timedelta(minutes=10)),
                "title": "Пазарите реагираат на царините",
                "description": "Follow-up angle.",
            },
        ]

        signals = build_cluster_source_signals(arts)

        assert signals[0]["trust_label"] == "Висока доверба"
        assert signals[0]["role_label"] in {"Најпотврден извор", "Водечки доверлив извор", "Прв извештај"}
        assert len(signals) == 3

    @patch("utils.get_source_health_map", return_value={})
    def test_annotate_cluster_articles_attaches_source_signal(self, _mock_health):
        now = datetime.datetime.now()
        arts = [
            {
                **_make_article("MIA", created_at=now),
                "title": "Тест наслов",
                "description": "Тест опис.",
            },
            {
                **_make_article("Makfax", created_at=now - datetime.timedelta(minutes=5)),
                "title": "Друг агол за темата",
                "description": "Тест опис 2.",
            },
        ]

        annotated = annotate_cluster_articles(arts)

        assert annotated[0]["source_signal"]["trust_label"]
        assert annotated[1]["source_signal"]["role_label"]


class TestReadNextClusters:
    @patch("utils.get_source_health_map", return_value={})
    def test_build_read_next_clusters_prefers_meaningful_shared_context(self, _mock_health):
        now = datetime.datetime.now()
        current_articles = [
            {
                **_make_article("MIA", created_at=now - datetime.timedelta(minutes=40)),
                "title": "Трамп најави царини за увоз",
                "description": "Главниот развој.",
                "entity_names": ["Трамп", "САД"],
                "topic": "Економија",
            },
            {
                **_make_article("Reuters", created_at=now - datetime.timedelta(minutes=30)),
                "title": "Реакции на најавата за царини",
                "description": "Контекст и реакции.",
                "entity_names": ["Трамп", "САД"],
                "topic": "Економија",
            },
        ]
        candidates = [
            {
                **_make_article("DW", created_at=now - datetime.timedelta(minutes=20)),
                "cluster_id": "next-1",
                "title": "Европските пазари реагираат на царините на Трамп",
                "description": "Следна фаза на истата тема.",
                "entity_names": ["Трамп", "ЕУ"],
                "cluster_tags": ["Трамп", "Царини"],
                "topic": "Економија",
            },
            {
                **_make_article("Press24", created_at=now - datetime.timedelta(minutes=10)),
                "cluster_id": "next-2",
                "title": "Сосема друга домашна тема",
                "description": "Нерелевантен кластер.",
                "entity_names": ["Скопје"],
                "cluster_tags": ["Скопје"],
                "topic": "Македонија",
            },
        ]

        result = build_read_next_clusters("current", current_articles, ["Трамп", "Царини"], candidates, limit=4)

        assert result
        assert result[0]["cluster_id"] == "next-1"
        assert result[0]["relationship_label"] in {"Следен развој", "Позадина и контекст", "Исти актери, друг агол"}

    @patch("utils.get_source_health_map", return_value={})
    def test_build_read_next_clusters_skips_weakly_related_noise(self, _mock_health):
        now = datetime.datetime.now()
        current_articles = [
            {
                **_make_article("MIA", created_at=now - datetime.timedelta(minutes=40)),
                "title": "Главен развој за Трамп",
                "description": "Главен опис.",
                "entity_names": ["Трамп"],
                "topic": "Свет",
            },
        ]
        candidates = [
            {
                **_make_article("Press24", created_at=now - datetime.timedelta(minutes=5)),
                "cluster_id": "noise-1",
                "title": "Локален спортски резултат",
                "description": "Без врска со темата.",
                "entity_names": ["Вардар"],
                "cluster_tags": ["Спорт"],
                "topic": "Спорт",
            },
        ]

        result = build_read_next_clusters("current", current_articles, ["Трамп"], candidates, limit=4)

        assert result == []


class TestSourceReputationRows:
    @patch("utils.get_source_health_map", return_value={})
    def test_build_source_reputation_rows_enriches_sources(self, _mock_health):
        source_rows = [
            {"name": "MIA", "country": "🇲🇰", "category": "Локални", "credibility": 2.0, "is_active": True},
            {"name": "Press24", "country": "🇲🇰", "category": "Локални", "credibility": 0.9, "is_active": True},
        ]
        pulse_rows = [{"source": "MIA", "count": 9}, {"source": "Press24", "count": 2}]
        speed_rows = [{"source": "MIA", "first_count": 12}, {"source": "Press24", "first_count": 1}]

        result = build_source_reputation_rows(source_rows, pulse_rows, speed_rows)

        assert result[0]["source"] == "MIA"
        assert result[0]["trust_tier"] == "Висока доверба"
        assert result[0]["recent_volume"] == 9
        assert result[0]["speed_first_count"] == 12
