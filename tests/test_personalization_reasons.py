from core.personalization_reasons import build_personalization_reasons


def test_build_personalization_reasons_followed_topic_and_source():
    profile = {
        "followedTopics": ["EU", "Mickoski"],
        "followedSources": ["Telma"],
        "recentClusters": [],
    }
    articles = [
        {"topic": "EU", "category": "Politika", "source": "Telma"},
        {"topic": "EU", "category": "Politika", "source": "Telma"},
    ]

    payload = build_personalization_reasons(profile=profile, articles=articles, lang="sr")

    assert payload["reason"].startswith("Praćena tema:")
    assert "EU" in payload["matched_topics"]
    assert "Telma" in payload["matched_sources"]
    assert payload["why_summary"] == "Zato što pratite: EU, Telma"


def test_build_personalization_reasons_semantic_fallback_mk():
    profile = {"followedTopics": [], "followedSources": [], "recentClusters": []}
    articles = [{"topic": "Ekonomija", "source": "A1"}]

    payload = build_personalization_reasons(
        profile=profile,
        articles=articles,
        lang="mk",
        similarity=0.61,
    )

    assert payload["reason"] == "Слично на приказните што неодамна ги читавте"
