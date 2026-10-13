from routes.home import _compact_home_cluster, _source_breakdown


def _articles(spec):
    return [{"source": source} for source, n in spec.items() for _ in range(n)]


def test_breakdown_counts_every_article_not_the_shipped_sample():
    cluster = {"cluster_id": "c1", "articles": _articles({"A": 5, "B": 3, "C": 1}), "source_count": 3}

    compact = _compact_home_cluster(cluster, max_articles=4)

    assert len(compact["articles"]) == 4  # payload stays a sample
    assert compact["source_breakdown"] == [
        {"source": "A", "count": 5},
        {"source": "B", "count": 3},
        {"source": "C", "count": 1},
    ]
    assert compact["source_breakdown_other"] == 0


def test_breakdown_keeps_top_sources_and_sums_the_remainder():
    spec = {f"S{i:02d}": 1 for i in range(20)}
    top, other = _source_breakdown(_articles(spec))

    assert len(top) == 8
    assert other == 12
    assert sum(item["count"] for item in top) + other == 20


def test_breakdown_ignores_blank_sources_and_non_dict_articles():
    top, other = _source_breakdown([{"source": " "}, {"source": None}, "x", {"source": "A"}])

    assert top == [{"source": "A", "count": 1}]
    assert other == 0
