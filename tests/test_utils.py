import pytest
import datetime
import math
from unittest.mock import patch, MagicMock
from utils import score_cluster, rank_articles_in_cluster, get_source_effective_weight


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
    def test_single_article_recent(self):
        arts = [_make_article()]
        s = score_cluster(arts)
        assert s > 0

    def test_more_sources_higher_score(self):
        one_source = [_make_article("MIA")]
        two_sources = [_make_article("MIA"), _make_article("Sitel")]
        assert score_cluster(two_sources) > score_cluster(one_source)

    def test_recency_decay(self):
        recent = [_make_article(created_at=datetime.datetime.now())]
        old = [_make_article(created_at=datetime.datetime.now() - datetime.timedelta(hours=24))]
        assert score_cluster(recent) > score_cluster(old)

    def test_click_bonus(self):
        no_clicks = [_make_article(clicks=0)]
        with_clicks = [_make_article(clicks=100)]
        assert score_cluster(with_clicks) > score_cluster(no_clicks)

    def test_credibility_matters(self):
        # MIA has credibility 2.0, Press24 has 0.9
        high_cred = [_make_article("MIA")]
        low_cred = [_make_article("Press24")]
        assert score_cluster(high_cred) > score_cluster(low_cred)

    def test_duplicate_sources_counted_once(self):
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

    def test_string_timestamp_fallback(self):
        """When created_at is an ISO string, it should still work."""
        arts = [_make_article()]
        arts[0]["created_at"] = datetime.datetime.now().isoformat()
        s = score_cluster(arts)
        assert s > 0

    def test_none_clicks_handled(self):
        arts = [_make_article()]
        arts[0]["clicks"] = None
        s = score_cluster(arts)
        assert s > 0

    def test_empty_list(self):
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


# ── rank_articles_in_cluster ──────────────────────────────────────

class TestRankArticles:
    def test_highest_credibility_first(self):
        arts = [
            _make_article("Press24"),   # 0.9
            _make_article("MIA"),       # 2.0
            _make_article("Sitel"),     # 1.7
        ]
        ranked = rank_articles_in_cluster(arts)
        assert ranked[0]["source"] == "MIA"
        assert ranked[1]["source"] == "Sitel"
        assert ranked[2]["source"] == "Press24"

    def test_single_article(self):
        arts = [_make_article("MIA")]
        ranked = rank_articles_in_cluster(arts)
        assert len(ranked) == 1
        assert ranked[0]["source"] == "MIA"

    def test_unknown_source_gets_default(self):
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
