from core.personalization_score import blend_personalization_score, score_cluster_for_profile


def test_score_cluster_for_profile_weights_followed_topic():
    profile = {
        "followedTopics": ["Ekonomija"],
        "followedSources": [],
        "recentClusters": [],
    }
    articles = [
        {"source": "Blic", "topic": "Ekonomija", "category": "Ekonomija"},
        {"source": "N1 Info", "topic": "Ekonomija", "category": "Ekonomija"},
    ]
    result = score_cluster_for_profile(
        profile=profile,
        articles=articles,
        metadata={"tags": []},
        lang="sr",
        cluster_id="cluster-a",
    )
    assert result["profile_score"] >= 3.2
    assert "Praćena tema" in result["reasons"][0]


def test_blend_personalization_score_prefers_semantic_weight():
    blended = blend_personalization_score(similarity=0.8, profile_score=1.0, semantic_weight=0.7)
    assert blended > 0.55
    assert blended < 0.8
