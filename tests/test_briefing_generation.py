#!/usr/bin/env python3

import tasks.delivery.briefing as briefing
from tasks.delivery import _load_daily_brief_clusters


class FakeBriefingDb:
    def __init__(self):
        self.execute_calls = []

    def execute(self, query, params=None, **kwargs):
        self.execute_calls.append((query, params))
        return []


def test_language_filtering(monkeypatch):
    """Test that the language filtering works correctly."""
    fake_db = FakeBriefingDb()
    monkeypatch.setattr(briefing, "db", fake_db)

    sr_clusters = _load_daily_brief_clusters(3, "sr")
    mk_clusters = _load_daily_brief_clusters(3, "mk")

    sr_cluster_ids = set(cluster["cluster_id"] for cluster in sr_clusters)
    mk_cluster_ids = set(cluster["cluster_id"] for cluster in mk_clusters)
    overlap = sr_cluster_ids.intersection(mk_cluster_ids)

    assert len(overlap) == 0, f"Found {len(overlap)} overlapping clusters between sr and mk"
    assert fake_db.execute_calls[0][1][2] == "RS"
    assert fake_db.execute_calls[1][1][2] == "MK"
