from tasks.intelligence.synthesis_merge import _split_cluster_merge_score


def test_split_cluster_merge_score_accepts_similar_clusters():
    import datetime

    now = datetime.datetime.now()
    left = {
        "cluster_id": "a",
        "country": "MK",
        "category": "Germanija",
        "topic": "vesti",
        "latest_article": now,
        "titles": [
            "Минибусот во кој беа фатени 500.000 евра на ГП Табановце, од Германија требало да стигне во Албанија"
        ],
        "tags": ["Минибусот", "Табановце", "Германија", "Албанија"],
        "centroid": [0.1] * 384,
    }
    right = {
        "cluster_id": "b",
        "country": "MK",
        "category": "Germanija",
        "topic": "vesti",
        "latest_article": now - datetime.timedelta(hours=12),
        "titles": [
            "Минибусот во кој беа најдени половина милион евра кеш возел од Германија кон Албанија, открива Николовски"
        ],
        "tags": ["Минибусот", "Германија", "Албанија", "Николовски"],
        "centroid": [0.11] * 384,
    }
    assert _split_cluster_merge_score(left, right, lang="mk") > 0


def test_split_cluster_merge_score_rejects_different_topics():
    left = {
        "cluster_id": "a",
        "country": "MK",
        "category": "Politika",
        "topic": "Politika",
        "titles": ["Vlada donela paket mera"],
        "tags": [],
    }
    right = {
        "cluster_id": "b",
        "country": "MK",
        "category": "Sport",
        "topic": "Sport",
        "titles": ["Fudbalerski klub pobedio"],
        "tags": [],
    }
    assert _split_cluster_merge_score(left, right, lang="mk") == 0.0
