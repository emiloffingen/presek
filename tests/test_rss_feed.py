from pathlib import Path


def test_rss_feed_requests_lang_and_dedupes_clusters():
    source = Path("web/src/pages/rss.xml.ts").read_text(encoding="utf-8")
    assert "lang=${lang}" in source
    assert "flatMap(cluster => cluster.articles" not in source
    assert "cluster.cluster_id" in source


def test_mk_rss_feed_dedupes_clusters():
    source = Path("web/src/pages/mk/rss.xml.ts").read_text(encoding="utf-8")
    assert "lang=mk" in source
    assert "flatMap(cluster => cluster.articles" not in source
    assert "cluster.cluster_id" in source
