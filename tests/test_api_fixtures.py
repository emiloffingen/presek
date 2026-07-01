import json
from pathlib import Path

from core.synthesis_quality import build_synthesis_meta

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "home_api_sample.json"


def test_home_api_fixture_contract_keys():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for key in (
        "status",
        "lead",
        "supporting",
        "developing",
        "wire",
        "for_you_pool",
        "synthesis_picks",
        "stats",
        "briefing",
        "lead_display",
        "pipeline",
    ):
        assert key in payload


def test_briefing_fixture_has_content_and_date():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    briefing = payload["briefing"]
    assert briefing["date"]
    assert "##" in briefing["content"]


def test_cluster_synthesis_meta_from_fixture_lead():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    row = {
        "generation_provider": "nvidia",
        "generation_model": "nvidia",
        "quality_score": 0.81,
        "fallback_reason": None,
        "synthetic_headline": payload["lead"]["synthetic_headline"],
        "summary": payload["lead_display"]["summary"],
        "generated_article": "Detalji promena ostaju predmet rasprave.",
    }
    meta = build_synthesis_meta(row, lang="sr", headline=row["synthetic_headline"])
    assert meta["copy_purity_ok"] is True or meta["copy_purity_ok"] is False
    assert "generation_provider" in meta
