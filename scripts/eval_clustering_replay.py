"""Replay articles through ingestion-time clustering and score the result.

Offline and read-only. Feeds articles in publication order through
``core.clustering.find_or_create_cluster`` the way ``core.ingestion`` does
(newest-first window of ``CLUSTER_LOOKBACK`` articles, simulated clock), then
reports:

* gold metrics on hand-labelled same-event groups
  (``tests/fixtures/clustering_regression.json``): pairwise precision / recall;
* window metrics on a full snapshot: near-duplicate pairs left in different
  clusters, clusters spanning more than 24h, clusters mixing clearly different
  stories, and the single-source share.

Usage:
    python scripts/eval_clustering_replay.py --dump snapshot.jsonl --hours 72   # read-only DB export
    python scripts/eval_clustering_replay.py --snapshot snapshot.jsonl
    python scripts/eval_clustering_replay.py --gold-only
    python scripts/eval_clustering_replay.py --snapshot s.jsonl --module path/to/old_clustering.py

The ingestion batch fast-path (``topic == "vesti"`` only) is not simulated;
every article goes through ``find_or_create_cluster``. Cluster centroids are
kept as running means, as ingestion does between its database reads (older
clustering modules ignore them).
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import itertools
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GOLD_PATH = os.path.join(ROOT, "tests", "fixtures", "clustering_regression.json")
NEAR_DUP_DISTANCE = 0.12  # raw local cosine distance: same article re-published
DIFFERENT_STORY_DISTANCE = 0.70  # below the 5th percentile of labelled different-story pairs


def _parse_time(value) -> dt.datetime:
    if isinstance(value, dt.datetime):
        moment = value
    else:
        moment = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def _distance(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 1.0 - dot / (na * nb) if na and nb else 1.0


def load_clustering(module_path: str | None):
    if not module_path:
        from core import clustering

        return clustering
    spec = importlib.util.spec_from_file_location("clustering_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(articles, clustering, lookback: int = 300) -> dict:
    """Assign a cluster to every article in time order; returns {article id: cluster id}."""
    # Pin the module clock to the replay time. Older versions read the wall clock
    # in _age_hours and ignore the ``now`` keyword; newer ones use ``now``.
    clock = {"now": None}

    def _age_hours(value, now=None, _clock=clock):
        if not value:
            return 0.0
        return max(0.0, ((now or _clock["now"]) - _parse_time(value)).total_seconds() / 3600)

    clustering._age_hours = _age_hours

    recent: list[dict] = []
    started: dict[str, dt.datetime] = {}
    # Running per-cluster centroids, as core.ingestion keeps them between DB reads.
    stats: dict = {}
    assigned: dict = {}
    for art in sorted(articles, key=lambda a: _parse_time(a["created_at"])):
        now = _parse_time(art["created_at"])
        clock["now"] = now
        kwargs = dict(
            embedding=art.get("embedding"),
            category=art.get("category"),
            source=art.get("source"),
            topic=art.get("topic"),
            now=now,
            cluster_stats=stats,
        )
        cid = clustering.find_or_create_cluster(None, art["title"], recent, **kwargs)
        started.setdefault(cid, now)
        _fold(stats, cid, art.get("embedding"), started[cid])
        assigned[art["id"]] = cid
        recent.insert(
            0,
            {
                "title": art["title"],
                "cluster_id": cid,
                "created_at": now,
                "category": art.get("category"),
                "topic": art.get("topic"),
                "embedding": art.get("embedding"),
                "cluster_started_at": started[cid],
            },
        )
        if len(recent) > lookback:
            recent.pop()
    return assigned


def _fold(stats: dict, cluster_id: str, vec, started_at) -> None:
    entry = stats.setdefault(cluster_id, {"centroid": [], "vectors": 0, "started_at": started_at})
    if not vec:
        return
    n = entry["vectors"]
    if n and len(entry["centroid"]) == len(vec):
        entry["centroid"] = [(c * n + v) / (n + 1) for c, v in zip(entry["centroid"], vec)]
    else:
        entry["centroid"], n = list(vec), 0
    entry["vectors"] = n + 1


def gold_metrics(gold: dict, assigned: dict) -> dict:
    related = {frozenset((a, b)) for group in gold.get("related", []) for a in group for b in group if a != b}
    tp = fp = fn = 0
    for a, b in itertools.combinations(gold["articles"], 2):
        same_label = a["label"] == b["label"]
        if not same_label and frozenset((a["label"], b["label"])) in related:
            continue
        same_cluster = assigned[a["id"]] == assigned[b["id"]]
        if same_label and same_cluster:
            tp += 1
        elif same_label:
            fn += 1
        elif same_cluster:
            fp += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    per_label = defaultdict(set)
    for art in gold["articles"]:
        per_label[art["label"]].add(assigned[art["id"]])
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "wrong_merges": fp,
        "missed_pairs": fn,
        "clusters_per_story": {k: len(v) for k, v in sorted(per_label.items())},
    }


def window_metrics(articles, assigned, since: dt.datetime) -> dict:
    scored = [a for a in articles if _parse_time(a["created_at"]) >= since]
    clusters = defaultdict(list)
    for art in scored:
        clusters[assigned[art["id"]]].append(art)

    split_pairs = 0
    by_time = sorted(scored, key=lambda a: _parse_time(a["created_at"]))
    for i, a in enumerate(by_time):
        ta = _parse_time(a["created_at"])
        for b in by_time[i + 1 :]:
            if (_parse_time(b["created_at"]) - ta).total_seconds() > 24 * 3600:
                break
            if assigned[a["id"]] != assigned[b["id"]] and _distance(a["embedding"], b["embedding"]) < NEAR_DUP_DISTANCE:
                split_pairs += 1

    long_span = mixed = 0
    big = [members for members in clusters.values() if len(members) >= 3]
    for members in big:
        times = [_parse_time(m["created_at"]) for m in members]
        if (max(times) - min(times)).total_seconds() > 24 * 3600:
            long_span += 1
        if any(
            _distance(x["embedding"], y["embedding"]) > DIFFERENT_STORY_DISTANCE
            for x, y in itertools.combinations(members, 2)
        ):
            mixed += 1
    single_source = sum(1 for members in clusters.values() if len({m.get("source") for m in members}) == 1)
    return {
        "articles": len(scored),
        "clusters": len(clusters),
        "single_source_pct": round(100 * single_source / max(len(clusters), 1), 1),
        "near_dup_pairs_split": split_pairs,
        "clusters_3plus": len(big),
        "clusters_3plus_spanning_24h": long_span,
        "clusters_3plus_mixing_stories": mixed,
    }


def dump_snapshot(path: str, hours: int) -> None:
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        from dotenv import dotenv_values

        url = dotenv_values(os.path.join(ROOT, ".env")).get("DATABASE_URL")
    with psycopg.connect(url, connect_timeout=10, options="-c default_transaction_read_only=on") as conn:
        rows = conn.execute(
            """SELECT id, cluster_id, title, source, category, topic, created_at, embedding::text
               FROM articles
               WHERE created_at > now() - make_interval(hours => %s) AND embedding IS NOT NULL
               ORDER BY created_at""",
            (hours,),
        ).fetchall()
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            vec = [float(x) for x in r[7].strip("[]").split(",")]
            fh.write(
                json.dumps(
                    {
                        "id": r[0],
                        "prod_cluster": r[1],
                        "title": r[2],
                        "source": r[3],
                        "category": r[4],
                        "topic": r[5],
                        "created_at": r[6].isoformat(),
                        "embedding": vec,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"wrote {len(rows)} articles to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", help="JSONL snapshot to replay (see --dump)")
    parser.add_argument("--dump", help="write a read-only DB snapshot to this path and exit")
    parser.add_argument("--hours", type=int, default=72, help="hours of articles to dump")
    parser.add_argument("--warmup-hours", type=float, default=24.0, help="replayed but not scored")
    parser.add_argument("--module", help="path to an alternative clustering.py (e.g. the old version)")
    parser.add_argument(
        "--lookback", type=int, default=4000, help="window cap in articles (production: CLUSTER_LOOKBACK over 24h)"
    )
    parser.add_argument("--gold-only", action="store_true")
    args = parser.parse_args()

    if args.dump:
        dump_snapshot(args.dump, args.hours)
        return

    clustering = load_clustering(args.module)
    with open(GOLD_PATH, encoding="utf-8") as fh:
        gold = json.load(fh)

    report = {}
    if args.snapshot and not args.gold_only:
        with open(args.snapshot, encoding="utf-8") as fh:
            articles = [json.loads(line) for line in fh]
        assigned = replay(articles, clustering, lookback=args.lookback)
        start = min(_parse_time(a["created_at"]) for a in articles)
        report["window"] = window_metrics(articles, assigned, start + dt.timedelta(hours=args.warmup_hours))
        gold_ids = {a["id"] for a in gold["articles"]}
        if gold_ids <= assigned.keys():
            report["gold_in_full_stream"] = gold_metrics(gold, assigned)
    report["gold_alone"] = gold_metrics(gold, replay(gold["articles"], clustering))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
