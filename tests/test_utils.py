import asyncio
import datetime
from unittest.mock import patch

import pytest

import utils
from utils import (
    annotate_cluster_articles,
    assess_cluster_synthesis_freshness,
    build_cluster_source_signals,
    build_read_next_clusters,
    build_source_reputation_rows,
    event_stream,
    get_source_effective_weight,
    get_source_trust_label,
    rank_articles_in_cluster,
    score_cluster,
    score_cluster_for_homepage,
    score_cluster_for_synthesis,
)


@pytest.fixture(autouse=True)
def clear_utils_cache():
    """Ensure every test starts with a clean cache to prevent pollution."""
    utils._SOURCE_STATUS_CACHE = {"time": 0.0, "data": {}}
    yield
    utils._SOURCE_STATUS_CACHE = {"time": 0.0, "data": {}}


def _make_article(source="N1 Info", created_at=None, clicks=0):
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
    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_single_article_recent(self, _mock_health):
        arts = [_make_article()]
        s = score_cluster(arts)
        assert s > 0

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_more_sources_higher_score(self, _mock_health):
        one_source = [_make_article("N1 Info")]
        two_sources = [_make_article("N1 Info"), _make_article("nova.rs")]
        assert score_cluster(two_sources) > score_cluster(one_source)

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_recency_decay(self, _mock_health):
        recent = [_make_article(created_at=datetime.datetime.now())]
        old = [_make_article(created_at=datetime.datetime.now() - datetime.timedelta(hours=24))]
        assert score_cluster(recent) > score_cluster(old)

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_click_bonus(self, _mock_health):
        no_clicks = [_make_article(clicks=0)]
        with_clicks = [_make_article(clicks=100)]
        assert score_cluster(with_clicks) > score_cluster(no_clicks)

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_credibility_matters(self, _mock_health):
        # MIA has credibility 2.0, Press24 has 0.9
        high_cred = [_make_article("N1 Info")]
        low_cred = [_make_article("Kurir")]
        assert score_cluster(high_cred) > score_cluster(low_cred)


def test_event_stream_stops_when_client_disconnects():
    class _FakePubSub:
        def __init__(self):
            self.closed = False
            self.unsubscribed = False
            self.calls = 0

        def subscribe(self, _channel):
            return None

        def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
            self.calls += 1
            return None

        def unsubscribe(self, _channel):
            self.unsubscribed = True

        def close(self):
            self.closed = True

    class _FakeRequest:
        def __init__(self):
            self.calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    async def _collect():
        pubsub = _FakePubSub()
        request = _FakeRequest()
        with patch.object(utils.redis_client, "pubsub", return_value=pubsub):
            stream = event_stream("updates", request=request)
            first = await stream.__anext__()
            with pytest.raises(StopAsyncIteration):
                await stream.__anext__()
        return first, pubsub

    first, pubsub = asyncio.run(_collect())
    assert first == "retry: 10000\n\n"
    assert pubsub.unsubscribed is True
    assert pubsub.closed is True

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_duplicate_sources_counted_once(self, _mock_health):
        """Same source appearing twice shouldn't double the credibility score."""
        two_same = [_make_article("N1 Info"), _make_article("N1 Info")]
        one = [_make_article("N1 Info")]
        # Breadth differs (log1p(2) vs log1p(1)), but cred_score is the same
        s_two = score_cluster(two_same)
        s_one = score_cluster(one)
        # The score difference should come only from breadth, not doubled credibility
        assert s_two > s_one  # more articles = more breadth
        # But ratio should be modest (log1p(2)/log1p(1) ≈ 1.58)
        assert s_two / s_one < 2.0

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_string_timestamp_fallback(self, _mock_health):
        """When created_at is an ISO string, it should still work."""
        arts = [_make_article()]
        arts[0]["created_at"] = datetime.datetime.now().isoformat()
        s = score_cluster(arts)
        assert s > 0

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_none_clicks_handled(self, _mock_health):
        arts = [_make_article()]
        arts[0]["clicks"] = None
        s = score_cluster(arts)
        assert s > 0

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_empty_list(self, _mock_health):
        """Empty article list should return 0 or a low score."""
        s = score_cluster([])
        assert s == 0 or s == 0.0

    @patch("utils.ranking.get_source_health_map", return_value={"N1 Info": {"quality_score": 0.3}})
    def test_source_health_penalizes_cluster_score(self, _mock_health):
        weak = [_make_article("N1 Info")]
        with patch("utils.get_source_health_map", return_value={}):
            strong_score = score_cluster(weak)
        weak_score = score_cluster(weak)
        assert weak_score < strong_score

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_synthesis_priority_prefers_richer_multi_source_cluster(self, _mock_health):
        shallow = [
            {
                **_make_article("N1 Info"),
                "title": "Tramp najavi govor",
                "description": "",
            },
            {
                **_make_article("N1 Info"),
                "title": "Tramp najavi govor",
                "description": "",
            },
        ]
        richer = [
            {
                **_make_article("N1 Info"),
                "title": "Tramp najavi govor za carini",
                "description": "Opis so povece detali za carinite.",
            },
            {
                **_make_article("Reuters"),
                "title": "Tramp ce objavi ekonomski merki vo Utorak",
                "description": "Vtoriot izvor dodava kontekst i reakcija.",
            },
            {
                **_make_article("DW"),
                "title": "Evropskite pazari reagiraat na najavata na Tramp",
                "description": "Tret izvor so poinakov akcenat.",
            },
        ]

        assert score_cluster_for_synthesis(richer) > score_cluster_for_synthesis(shallow)

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_synthesis_priority_rewards_title_divergence(self, _mock_health):
        aligned = [
            {
                **_make_article("N1 Info"),
                "title": "Tramp najavi govor za carini",
                "description": "Opis eden.",
            },
            {
                **_make_article("Reuters"),
                "title": "Tramp najavi govor za carini",
                "description": "Opis dva.",
            },
        ]
        divergent = [
            {
                **_make_article("N1 Info"),
                "title": "Tramp najavi govor za carini",
                "description": "Opis eden.",
            },
            {
                **_make_article("Reuters"),
                "title": "Pazarite reagiraat na govorot na Tramp i novite merki",
                "description": "Opis dva.",
            },
        ]

        assert score_cluster_for_synthesis(divergent) > score_cluster_for_synthesis(aligned)

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_homepage_priority_prefers_corroborated_multi_source_cluster(self, _mock_health):
        thin = [
            {
                **_make_article("Kurir"),
                "title": "Tramp najavi merki",
                "description": "",
            },
            {
                **_make_article(
                    "Kurir",
                    created_at=datetime.datetime.now() - datetime.timedelta(minutes=5),
                ),
                "title": "Tramp najavi novi merki",
                "description": "",
            },
        ]
        richer = [
            {
                **_make_article("N1 Info"),
                "title": "Tramp najavi novi carini",
                "description": "Glaven razvoj so detali.",
            },
            {
                **_make_article(
                    "Reuters",
                    created_at=datetime.datetime.now() - datetime.timedelta(minutes=8),
                ),
                "title": "Reuters pisuva za reakciite i rokot za novite carini",
                "description": "Vtor izvor so siri kontekst.",
            },
            {
                **_make_article(
                    "DW",
                    created_at=datetime.datetime.now() - datetime.timedelta(minutes=12),
                ),
                "title": "Evropskite pazari reagiraat na najavenite carini",
                "description": "Tret izvor so potvrda i posledica.",
            },
        ]

        assert score_cluster_for_homepage(richer) > score_cluster_for_homepage(thin)

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_homepage_priority_penalizes_single_source_churn(self, _mock_health):
        single_source = [
            {
                **_make_article("Kurir"),
                "title": "Kratka vest za razvojot",
                "description": "",
            },
            {
                **_make_article(
                    "Kurir",
                    created_at=datetime.datetime.now() - datetime.timedelta(minutes=3),
                ),
                "title": "jos kratok follow-up za razvojot",
                "description": "",
            },
        ]
        broader = [
            {
                **_make_article("Politika"),
                "title": "Glaven razvoj vo temata",
                "description": "Opis eden.",
            },
            {
                **_make_article(
                    "N1 Info",
                    created_at=datetime.datetime.now() - datetime.timedelta(minutes=6),
                ),
                "title": "Vtor izvor ga potvrduva glavni razvoj",
                "description": "Opis dva.",
            },
        ]

        assert score_cluster_for_homepage(broader) > score_cluster_for_homepage(single_source)


# ── rank_articles_in_cluster ──────────────────────────────────────


class TestRankArticles:
    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_highest_credibility_first(self, _mock_health):
        arts = [
            _make_article("Kurir"),  # 0.9
            _make_article("N1 Info"),  # 2.0
            _make_article("nova.rs"),  # 1.7
        ]
        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "N1 Info"
        assert ranked[1]["source"] == "nova.rs"
        assert ranked[2]["source"] == "Kurir"

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_single_article(self, _mock_health):
        arts = [_make_article("N1 Info")]
        ranked = rank_articles_in_cluster(arts)
        assert len(ranked) == 1
        assert ranked[0]["source"] == "N1 Info"

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_unknown_source_gets_default(self, _mock_health):
        arts = [_make_article("Unknown"), _make_article("N1 Info")]
        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "N1 Info"  # 2.0 > 0.8 default

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_richer_corroborated_article_can_beat_thin_variant(self, _mock_health):
        now = datetime.datetime.now()
        arts = [
            {
                **_make_article("Politika", created_at=now),
                "title": "Tramp najavi merki",
                "description": "",
            },
            {
                **_make_article("N1 Info", created_at=now - datetime.timedelta(minutes=4)),
                "title": "Tramp najavi merki za carini i reakciite",
                "description": "Opis so povece detali, rokovi i reakcija na pazarite.",
            },
            {
                **_make_article("Reuters", created_at=now - datetime.timedelta(minutes=6)),
                "title": "Reakciite na pazarite po najavenite carini na Tramp",
                "description": "Vtor izvor sto ga potvrduva glavni razvoj i dodava kontekst.",
            },
        ]

        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "N1 Info"

    @patch("utils.ranking.get_source_health_map", return_value={"N1 Info": {"quality_score": 0.25}})
    def test_source_health_can_reorder_articles(self, _mock_health):
        arts = [_make_article("N1 Info"), _make_article("nova.rs")]
        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "nova.rs"


class TestSourceEffectiveWeight:
    @patch("utils.ranking.get_source_health_map", return_value={"N1 Info": {"quality_score": 0.2}})
    def test_effective_weight_uses_health_multiplier(self, _mock_health):
        assert get_source_effective_weight("N1 Info") < 2.0

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_trust_label_reflects_source_weight(self, _mock_health):
        assert get_source_trust_label("N1 Info") == "Visoko poverenje"
        assert get_source_trust_label("Politika") == "Potvrden izvor"
        assert get_source_trust_label("Kurir") == "sledeci izvor"


class TestSynthesisFreshness:
    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_missing_synthesis_requests_refresh(self, _mock_health):
        arts = [
            {
                **_make_article("N1 Info"),
                "title": "Tramp najavi novi carini",
                "description": "Prv izvestaj so glavni razvoj.",
            },
            {
                **_make_article("Reuters"),
                "title": "reakcije po najavata na Tramp",
                "description": "Vtor izvor so kontekst.",
            },
        ]

        result = assess_cluster_synthesis_freshness(arts, None)

        assert result["refresh_needed"] is True
        assert "missing_synthesis" in result["reasons"]

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_no_new_articles_keeps_synthesis_fresh(self, _mock_health):
        created_at = datetime.datetime.now() - datetime.timedelta(minutes=30)
        arts = [
            {
                **_make_article("N1 Info", created_at=created_at),
                "title": "Tramp najavi carini",
                "description": "Opis.",
            },
            {
                **_make_article("Reuters", created_at=created_at),
                "title": "reakcije na carinite",
                "description": "Opis.",
            },
        ]

        result = assess_cluster_synthesis_freshness(arts, created_at)

        assert result["refresh_needed"] is False
        assert result["new_article_count"] == 0

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_new_source_and_numbers_mark_cluster_stale(self, _mock_health):
        synthesis_time = datetime.datetime.now() - datetime.timedelta(hours=2)
        old_time = synthesis_time - datetime.timedelta(minutes=30)
        new_time = synthesis_time + datetime.timedelta(minutes=25)
        arts = [
            {
                **_make_article("N1 Info", created_at=old_time),
                "title": "Vladata najavi paket od 100 milioni",
                "description": "Prv izvestaj za paketot.",
            },
            {
                **_make_article("Reuters", created_at=new_time),
                "title": "Reuters pisuva za 120 milioni i nov rok",
                "description": "Se dodava druga brojka i nov izvor.",
            },
        ]

        result = assess_cluster_synthesis_freshness(arts, synthesis_time)

        assert result["refresh_needed"] is True
        assert "new_sources" in result["reasons"]
        assert "new_numbers" in result["reasons"]

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_single_quick_followup_does_not_force_refresh_in_cooldown(self, _mock_health):
        synthesis_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
        arts = [
            {
                **_make_article("N1 Info", created_at=synthesis_time - datetime.timedelta(minutes=5)),
                "title": "Tramp najavi carini",
                "description": "Prv izvestaj.",
            },
            {
                **_make_article("N1 Info", created_at=synthesis_time + datetime.timedelta(minutes=4)),
                "title": "Tramp najavi carini za uvoz",
                "description": "Malo dopolnuvanje bez nov izvor.",
            },
        ]

        result = assess_cluster_synthesis_freshness(arts, synthesis_time)

        assert result["refresh_needed"] is False


class TestSourceSignals:
    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_build_cluster_source_signals_marks_lead_and_trust(self, _mock_health):
        now = datetime.datetime.now()
        arts = [
            {
                **_make_article("N1 Info", created_at=now - datetime.timedelta(minutes=30)),
                "title": "Tramp najavi carini",
                "description": "Prv izvestaj.",
            },
            {
                **_make_article("Reuters", created_at=now - datetime.timedelta(minutes=20)),
                "title": "reakcije na carinite i novite merki na Tramp",
                "description": "Vtoriot izvor nosi dopolnitelen kontekst.",
            },
            {
                **_make_article("Kurir", created_at=now - datetime.timedelta(minutes=10)),
                "title": "Pazarite reagiraat na carinite",
                "description": "Follow-up angle.",
            },
        ]

        signals = build_cluster_source_signals(arts)

        assert signals[0]["trust_label"] == "Visoko poverenje"
        assert signals[0]["role_label"] in {
            "Najpotvrden izvor",
            "Vodecki doverliv izvor",
            "Prv izvestaj",
        }
        assert len(signals) == 3

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_annotate_cluster_articles_attaches_source_signal(self, _mock_health):
        now = datetime.datetime.now()
        arts = [
            {
                **_make_article("N1 Info", created_at=now),
                "title": "Test naslov",
                "description": "Test opis.",
            },
            {
                **_make_article("Politika", created_at=now - datetime.timedelta(minutes=5)),
                "title": "Drug ugao za temata",
                "description": "Test opis 2.",
            },
        ]

        annotated = annotate_cluster_articles(arts)

        assert annotated[0]["source_signal"]["trust_label"]
        assert annotated[1]["source_signal"]["role_label"]


class TestReadNextClusters:
    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_build_read_next_clusters_prefers_meaningful_shared_context(self, _mock_health):
        now = datetime.datetime.now()
        current_articles = [
            {
                **_make_article("N1 Info", created_at=now - datetime.timedelta(minutes=40)),
                "title": "Tramp najavi carini za uvoz",
                "description": "glavni razvoj.",
                "entity_names": ["Tramp", "SAD"],
                "topic": "Ekonomija",
            },
            {
                **_make_article("Reuters", created_at=now - datetime.timedelta(minutes=30)),
                "title": "reakcije na najavata za carini",
                "description": "kontekst i reakcije.",
                "entity_names": ["Tramp", "SAD"],
                "topic": "Ekonomija",
            },
        ]
        candidates = [
            {
                **_make_article("DW", created_at=now - datetime.timedelta(minutes=20)),
                "cluster_id": "next-1",
                "title": "Evropskite pazari reagiraat na carinite na Tramp",
                "description": "Sledna faza na istata tema.",
                "entity_names": ["Tramp", "EU"],
                "cluster_tags": ["Tramp", "Carini"],
                "topic": "Ekonomija",
            },
            {
                **_make_article("Kurir", created_at=now - datetime.timedelta(minutes=10)),
                "cluster_id": "next-2",
                "title": "Sosema druga domasna tema",
                "description": "Nerelevanten klaster.",
                "entity_names": ["Beograd"],
                "cluster_tags": ["Beograd"],
                "topic": "Srbija",
            },
        ]

        result = build_read_next_clusters("current", current_articles, ["Tramp", "Carini"], candidates, limit=4)

        assert result
        assert result[0]["cluster_id"] == "next-1"
        assert result[0]["relationship_label"] in {
            "Sleden razvoj",
            "pozadina i kontekst",
            "Isti akteri",
        }

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_build_read_next_clusters_skips_weakly_related_noise(self, _mock_health):
        now = datetime.datetime.now()
        current_articles = [
            {
                **_make_article("N1 Info", created_at=now - datetime.timedelta(minutes=40)),
                "title": "Glaven razvoj za Tramp",
                "description": "Glaven opis.",
                "entity_names": ["Tramp"],
                "topic": "Svet",
            },
        ]
        candidates = [
            {
                **_make_article("Kurir", created_at=now - datetime.timedelta(minutes=5)),
                "cluster_id": "noise-1",
                "title": "Lokalen sportski rezultat",
                "description": "Bez vrska so temata.",
                "entity_names": ["Vardar"],
                "cluster_tags": ["Sport"],
                "topic": "Sport",
            },
        ]

        result = build_read_next_clusters("current", current_articles, ["Tramp"], candidates, limit=4)

        assert result == []

    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_build_read_next_clusters_ignores_generic_vesti_only_match(self, _mock_health):
        now = datetime.datetime.now()
        current_articles = [
            {
                **_make_article("Telma", created_at=now - datetime.timedelta(minutes=40)),
                "title": "Минибус со пари запленет на Табановце",
                "description": "Opis.",
                "entity_names": [],
                "topic": "vesti",
            },
        ]
        candidates = [
            {
                **_make_article("Kanal 5", created_at=now - datetime.timedelta(minutes=5)),
                "cluster_id": "noise-v",
                "title": "Резервоар пукна во фабрика во САД, има загинати",
                "description": "Unrelated generic news.",
                "entity_names": [],
                "cluster_tags": [],
                "topic": "vesti",
            },
        ]

        result = build_read_next_clusters("current", current_articles, [], candidates, limit=4)

        assert result == []


class TestSourceReputationRows:
    @patch("utils.ranking.get_source_health_map", return_value={})
    def test_build_source_reputation_rows_enriches_sources(self, _mock_health):
        source_rows = [
            {
                "name": "N1 Info",
                "country": "RS",
                "category": "Lokalni",
                "credibility": 2.0,
                "is_active": True,
            },
            {
                "name": "Kurir",
                "country": "RS",
                "category": "Lokalni",
                "credibility": 0.9,
                "is_active": True,
            },
        ]
        pulse_rows = [{"source": "N1 Info", "count": 9}, {"source": "Kurir", "count": 2}]
        speed_rows = [
            {"source": "N1 Info", "first_count": 12},
            {"source": "Kurir", "first_count": 1},
        ]
        history_rows = [
            {
                "source": "N1 Info",
                "lead_count_30d": 10,
                "corroborated_lead_count_30d": 8,
                "solo_lead_count_30d": 2,
                "recent_7d_volume": 14,
                "previous_7d_volume": 8,
            },
            {
                "source": "Kurir",
                "lead_count_30d": 5,
                "corroborated_lead_count_30d": 1,
                "solo_lead_count_30d": 4,
                "recent_7d_volume": 2,
                "previous_7d_volume": 9,
            },
        ]

        result = build_source_reputation_rows(source_rows, pulse_rows, speed_rows, history_rows)

        assert result[0]["source"] == "N1 Info"
        assert result[0]["trust_tier"] == "Visoko poverenje"
        assert result[0]["recent_volume"] == 9
        assert result[0]["speed_first_count"] == 12
        assert result[0]["corroboration_rate"] == 0.8
        assert result[0]["lone_lead_rate"] == 0.2
        assert result[0]["trend_label"] == "Raste"
        assert result[0]["tendency"] == "Cesto prv na prikaznata"
        assert result[1]["trend_label"] == "Slabee"
        assert result[1]["lone_lead_rate"] == 0.8


def test_event_stream_yields_published_events():
    import asyncio
    from unittest.mock import patch

    import utils
    from utils.cache import event_stream

    class _FakePubSub:
        def __init__(self):
            self.closed = False
            self.unsubscribed = False
            self.calls = 0

        def subscribe(self, _channel):
            return None

        def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
            self.calls += 1
            if self.calls == 1:
                return {
                    "type": "message",
                    "pattern": None,
                    "channel": b"updates",
                    "data": '{"type": "new_article", "title": "Test Title"}',
                }
            return None

        def unsubscribe(self, _channel):
            self.unsubscribed = True

        def close(self):
            self.closed = True

    class _FakeRequest:
        async def is_disconnected(self):
            return False

    async def _collect():
        pubsub = _FakePubSub()
        request = _FakeRequest()
        with patch.object(utils.redis_client, "pubsub", return_value=pubsub):
            stream = event_stream("updates", request=request)
            first = await stream.__anext__()
            return first, pubsub

    first, pubsub = asyncio.run(_collect())
    assert "data: {" in first
    assert "Test Title" in first
    assert pubsub.closed is True
