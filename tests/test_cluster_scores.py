"""Unit tests for compute_cluster_pulse_pluralism (utils/ranking.py)."""

import datetime
from unittest.mock import patch

from utils.ranking import compute_cluster_pulse_pluralism

_NOW = datetime.datetime.now(datetime.timezone.utc)


def _row(source, hours_ago=1.0):
    ts = (_NOW - datetime.timedelta(hours=hours_ago)).isoformat()
    return {"source": source, "created_at": ts, "ingested_at": ts}


_REG = {
    "MIA": {"category": "Agencijski"},
    "Expres": {"category": "Nezavisni"},
    "Libertas": {"category": "Lokalni"},
    "Kurir": {"category": "Nezavisni"},
}


def test_empty_rows_fall_back_to_defaults():
    assert compute_cluster_pulse_pluralism([]) == {"pulse_score": 50.0, "pluralism_score": 50.0}
    assert compute_cluster_pulse_pluralism(None) == {"pulse_score": 50.0, "pluralism_score": 50.0}


def test_pluralism_rewards_sources_and_tier_spread():
    with patch("utils.ranking.get_source_registry", return_value=_REG):
        one = compute_cluster_pulse_pluralism([_row("MIA")])
        three = compute_cluster_pulse_pluralism([_row("MIA"), _row("Expres"), _row("Libertas")])
    assert one["pluralism_score"] < three["pluralism_score"]
    assert three["pluralism_score"] == 75.0  # 10 + 45 + 20
    # Same-tier reprints score lower than cross-tier coverage.
    with patch("utils.ranking.get_source_registry", return_value=_REG):
        same_tier = compute_cluster_pulse_pluralism([_row("Expres"), _row("Kurir")])
    assert same_tier["pluralism_score"] == 40.0  # 10 + 30 + 0
    assert same_tier["pluralism_score"] < three["pluralism_score"]


def test_pulse_rewards_velocity_and_recency():
    with patch("utils.ranking.get_source_registry", return_value=_REG):
        hot = compute_cluster_pulse_pluralism([_row("MIA", 0.2) for _ in range(6)])
        cold = compute_cluster_pulse_pluralism([_row("MIA", 72.0)])
    assert hot["pulse_score"] > cold["pulse_score"]
    assert hot["pulse_score"] == 75.0  # 10 + 50 + 15
    assert cold["pulse_score"] == 10.0  # 10 + 0 + 0


def test_scores_stay_in_range():
    rows = [_row(f"S{i}", 0.1) for i in range(30)]
    with patch("utils.ranking.get_source_registry", return_value={}):
        out = compute_cluster_pulse_pluralism(rows)
    assert 0.0 <= out["pulse_score"] <= 100.0
    assert 0.0 <= out["pluralism_score"] <= 100.0
