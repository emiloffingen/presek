from core.trust_signals import build_trust_summary


def test_trust_summary_consensus_tier():
    summary = build_trust_summary(
        sources_count=5,
        pluralism_score=10,
        is_stale=False,
        has_verification=True,
        lang="sr",
    )
    assert summary["tier"] == "consensus"
    assert summary["score"] >= 70
    assert "5 izvora" in summary["detail"]


def test_trust_summary_early_tier_mk():
    summary = build_trust_summary(sources_count=1, lang="mk")
    assert summary["tier"] == "early"
    assert "Ран сигнал" in summary["label"]
