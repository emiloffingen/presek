import json
from pathlib import Path

from core.synthesis_quality import build_synthesis_meta
from core.trust_signals import build_trust_summary

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "cluster_api_sample.json"


def test_cluster_api_fixture_contract_keys():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cluster = payload["data"]
    for key in (
        "cluster_id",
        "synthetic_headline",
        "articles",
        "synthesis_meta",
        "trust_summary",
        "synthesis",
        "perspectives",
    ):
        assert key in cluster


def test_cluster_trust_summary_fixture_matches_builder():
    cluster = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["data"]
    trust = cluster["trust_summary"]
    rebuilt = build_trust_summary(
        sources_count=trust["sources_count"],
        pluralism_score=trust["pluralism_score"],
        is_stale=trust["is_stale"],
        has_verification=trust["has_verification"],
        is_provisional=trust["is_provisional"],
        lang="sr",
    )
    for key in ("score", "tier", "label", "detail", "sources_count", "pluralism_score"):
        assert key in rebuilt
    assert rebuilt["tier"] == trust["tier"]


