import json
from pathlib import Path

from core.personalization_score import blend_personalization_score, score_cluster_for_profile


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "profile_api_sample.json"


def test_profile_api_fixture_contract_keys():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload["results"], list)
    item = payload["results"][0]
    for key in (
        "cluster_id",
        "articles",
        "similarity",
        "profile_score",
        "blend_score",
        "reason",
        "match_reasons",
        "has_synthesis",
        "seen",
    ):
        assert key in item


def test_profile_fixture_scores_match_server_helpers():
    item = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["results"][0]
    profile = {
        "followedTopics": ["Ekonomija"],
        "followedSources": [],
        "recentClusters": [],
    }
    scored = score_cluster_for_profile(
        profile=profile,
        articles=item["articles"],
        metadata={},
        lang="sr",
        cluster_id=item["cluster_id"],
    )
    blend = blend_personalization_score(
        similarity=item["similarity"],
        profile_score=scored["profile_score"],
    )
    assert scored["profile_score"] >= 3.0
    assert 0.0 <= blend <= 1.0
    assert item["blend_score"] == round(blend, 2) or abs(item["blend_score"] - blend) < 0.05
