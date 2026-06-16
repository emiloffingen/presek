from core.personalization_score import blend_personalization_score, score_cluster_for_profile
from core.synthesis_quality import build_synthesis_meta
from core.trust_signals import build_trust_summary


def test_personalized_result_contract_fields():
    profile = {"followedTopics": ["Ekonomija"], "followedSources": [], "recentClusters": []}
    articles = [{"source": "Blic", "topic": "Ekonomija", "category": "Ekonomija"}]
    scored = score_cluster_for_profile(profile=profile, articles=articles, metadata={}, lang="sr", cluster_id="c-1")
    blend = blend_personalization_score(similarity=0.71, profile_score=scored["profile_score"])

    payload = {
        "cluster_id": "c-1",
        "similarity": 0.71,
        "profile_score": scored["profile_score"],
        "blend_score": blend,
        "reason": "Praćena tema: Ekonomija",
        "match_reasons": scored["reasons"],
    }

    for key in ("cluster_id", "similarity", "profile_score", "blend_score", "reason", "match_reasons"):
        assert key in payload
    assert 0.0 <= payload["blend_score"] <= 1.0


def test_synthesis_meta_contract_includes_copy_purity():
    row = {
        "generation_provider": "local",
        "generation_model": "gemma",
        "quality_score": 0.82,
        "fallback_reason": None,
        "synthetic_headline": "Vlada usvojila izmene",
        "summary": "Izvori potvrđuju promene.",
        "generated_article": "Detalji promena ostaju predmet rasprave u parlamentu.",
    }
    meta = build_synthesis_meta(row, lang="sr")
    for key in (
        "lang",
        "generation_provider",
        "quality_score",
        "is_provisional",
        "needs_upgrade",
        "copy_purity_ok",
        "copy_purity_score",
        "copy_purity_reason",
    ):
        assert key in meta


def test_trust_summary_contract():
    trust = build_trust_summary(
        sources_count=3,
        pluralism_score=18,
        is_stale=False,
        has_verification=True,
        is_provisional=False,
        lang="sr",
    )
    for key in ("score", "tier", "label", "detail", "sources_count", "pluralism_score"):
        assert key in trust
    assert trust["tier"] in {"consensus", "verified", "plural", "early"}
