from core.trust_signals import build_trust_summary


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
