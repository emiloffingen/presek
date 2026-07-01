import json
from pathlib import Path

ADMIN_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "admin_dashboard_sample.json"
TRACE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthesis_trace_sample.json"


def test_admin_dashboard_fixture_contract_keys():
    payload = json.loads(ADMIN_FIXTURE.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    for key in ("ai", "scrapers", "tasks", "db", "redis", "articles", "clusters", "queues", "ops", "system"):
        assert key in payload
    assert "current_provider" in payload["ai"]
    assert "failed_tasks" in payload["tasks"]


def test_synthesis_trace_fixture_contract_keys():
    payload = json.loads(TRACE_FIXTURE.read_text(encoding="utf-8"))
    for key in (
        "cluster_id",
        "lang",
        "article_count",
        "unique_sources",
        "freshness",
        "languages",
        "history",
        "recommended_actions",
    ):
        assert key in payload
    assert payload["languages"][0]["generation_provider"]
