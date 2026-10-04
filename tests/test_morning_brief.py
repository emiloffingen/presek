import datetime

from tasks.delivery import morning_brief as mb


def _c(title, topic, score, cid="c"):
    return {
        "cluster_id": cid,
        "title": title,
        "topic": topic,
        "score": score,
        "source": "Извор",
        "source_count": 2,
        "cluster_summary": "кратко резиме",
    }


def test_pick_caps_and_dedupes(monkeypatch):
    data = [
        _c("A", "x", 9, "1"),
        _c("a", "y", 8, "2"),   # near-dup of A
        _c("B", "x", 7, "3"),
        _c("C", "x", 6, "4"),   # third topic x -> dropped
        _c("D", "z", 5, "5"),
        _c("E", "w", 4, "6"),
    ]
    monkeypatch.setattr(mb, "_load_weekly_digest_clusters", lambda limit=28: data)
    picked = mb.pick_morning_clusters(limit=3)
    assert len(picked) == 3
    assert sum(1 for c in picked if c["topic"] == "x") <= 2
    assert [c["title"] for c in picked][0] == "A"


def test_render_escapes_and_links():
    clusters = [_c("Наслов <b>", "x", 9, "cid1")]
    html = mb.render_morning_brief_html(clusters, datetime.datetime(2026, 10, 4), "https://x/unsub")
    assert "Наслов &lt;b&gt;" in html
    assert "/mk/cluster/cid1" in html
    assert "https://x/unsub" in html


def test_mk_date():
    assert mb._mk_date(datetime.datetime(2026, 10, 4)) == "4 октомври 2026"
