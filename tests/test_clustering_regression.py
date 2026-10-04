"""Clustering regression set built from real production articles (2026-10-01..04).

The fixture holds hand-labelled same-event groups with their stored embeddings.
Replaying them in publication order through ``find_or_create_cluster`` must keep
different stories about the same person apart (the name-anchored "bags" seen in
production) while still joining re-published and reworded headlines.
"""

import datetime
import itertools
import json
import os

from core.clustering import MAX_CLUSTER_AGE_HOURS, find_or_create_cluster

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "clustering_regression.json")


def _load():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _time(value):
    return datetime.datetime.fromisoformat(value).replace(tzinfo=datetime.timezone.utc)


def _replay(articles):
    recent, assigned = [], {}
    for art in sorted(articles, key=lambda a: a["created_at"]):
        now = _time(art["created_at"])
        cid = find_or_create_cluster(
            None,
            art["title"],
            recent,
            embedding=art["embedding"],
            category=art["category"],
            topic=art["topic"],
            source=art["source"],
            now=now,
        )
        assigned[art["id"]] = cid
        recent.insert(
            0,
            {
                "title": art["title"],
                "cluster_id": cid,
                "created_at": now,
                "category": art["category"],
                "topic": art["topic"],
                "embedding": art["embedding"],
            },
        )
    return assigned


def _clusters_by_label(data, assigned):
    out = {}
    for art in data["articles"]:
        out.setdefault(art["label"], set()).add(assigned[art["id"]])
    return out


def test_same_person_different_stories_stay_apart():
    data = _load()
    by_label = _clusters_by_label(data, _replay(data["articles"]))
    related = {frozenset((a, b)) for g in data["related"] for a in g for b in g if a != b}
    # Three different Ѓорѓиевски stories and Мицкоски stories: production merged
    # these on the shared name. Pairs the fixture marks as related are skipped.
    for left, right in itertools.combinations(
        ["vendors", "booing", "bridge_deadline", "mickoski_fuel", "bridge_visit"], 2
    ):
        if frozenset((left, right)) in related:
            continue
        assert not by_label[left] & by_label[right], (left, right)
    assert not by_label["fan_fight"] & by_label["fan_donation"]


def test_republished_headlines_join_their_twin():
    data = _load()
    by_label = _clusters_by_label(data, _replay(data["articles"]))
    assert len(by_label["70yo_found"]) == 1
    assert len(by_label["booing"]) == 1
    assert len(by_label["prilep_depot_fire"]) == 1


def test_pairwise_quality_floor():
    data = _load()
    assigned = _replay(data["articles"])
    related = {frozenset((a, b)) for g in data["related"] for a in g for b in g if a != b}
    tp = fp = fn = 0
    for a, b in itertools.combinations(data["articles"], 2):
        same_label = a["label"] == b["label"]
        if not same_label and frozenset((a["label"], b["label"])) in related:
            continue
        same_cluster = assigned[a["id"]] == assigned[b["id"]]
        tp += same_label and same_cluster
        fn += same_label and not same_cluster
        fp += same_cluster and not same_label
    # Before the semantic gate this set scored precision 0.85 / recall 0.78.
    assert tp / (tp + fp) >= 0.93
    assert tp / (tp + fn) >= 0.75


def test_identical_headline_matches_any_member_not_only_the_seed():
    now = datetime.datetime(2026, 10, 3, 13, 0, tzinfo=datetime.timezone.utc)
    recent = [
        {
            "cluster_id": "bridge",
            "title": "Ѓорѓиевски: Мостот на „Љубљанска“ во функција до крајот на годината",
            "category": "Makedonija",
            "topic": "Politika",
            "created_at": now - datetime.timedelta(hours=1),
        },
        {
            "cluster_id": "bridge",
            "title": "Мицкоски на увид на градежни активности на мостот на улица „Љубљанска“ во Карпош",
            "category": "Makedonija",
            "topic": "Politika",
            "created_at": now - datetime.timedelta(hours=5),
        },
    ]
    assert (
        find_or_create_cluster(
            None,
            "Ѓорѓиевски: Мостот на „Љубљанска“ во функција до крајот на годината",
            recent,
            category="Makedonija",
            topic="Politika",
            now=now,
        )
        == "bridge"
    )


def test_cluster_stops_accepting_articles_after_max_age():
    now = datetime.datetime(2026, 10, 4, 12, 0, tzinfo=datetime.timezone.utc)
    recent = [
        {
            "cluster_id": "old-story",
            "title": "Изменет сообраќаен режим во Скопје поради маратонот",
            "category": "Makedonija",
            "topic": "vesti",
            "created_at": now - datetime.timedelta(hours=2),
            "cluster_started_at": now - datetime.timedelta(hours=MAX_CLUSTER_AGE_HOURS + 1),
        }
    ]
    assert (
        find_or_create_cluster(
            None,
            "Изменет сообраќаен режим во Скопје поради маратонот",
            recent,
            category="Makedonija",
            topic="vesti",
            now=now,
        )
        != "old-story"
    )


def test_cluster_stats_centroid_gates_a_name_only_match():
    now = datetime.datetime(2026, 10, 3, 13, 0, tzinfo=datetime.timezone.utc)
    recent = [
        {
            "cluster_id": "booing",
            "title": "Советниците на Левица го исвиркаа Ѓорѓиевски",
            "category": "Makedonija",
            "topic": "vesti",
            "created_at": now - datetime.timedelta(hours=1),
        }
    ]
    stats = {"booing": {"centroid": [1.0, 0.0, 0.0], "started_at": now - datetime.timedelta(hours=1)}}
    # Orthogonal embedding: shares the name but is a different story.
    assert (
        find_or_create_cluster(
            None,
            "Ѓорѓиевски најави акција против дивите продавачи",
            recent,
            embedding=[0.0, 1.0, 0.0],
            category="Makedonija",
            topic="vesti",
            now=now,
            cluster_stats=stats,
        )
        != "booing"
    )
