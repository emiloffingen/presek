from tasks.delivery.briefing import _dedupe_briefing_candidates


def _c(title, topic="t", score=5.0, **extra):
    return {"title": title, "topic": topic, "score": score, **extra}


def test_caps_to_limit():
    cands = [_c(f"Story {i}", topic=f"t{i}") for i in range(10)]
    assert len(_dedupe_briefing_candidates(cands, limit=4)) == 4


def test_dedupes_case_insensitive_titles():
    cands = [_c("Same headline", topic="a"), _c("same headline", topic="b")]
    assert len(_dedupe_briefing_candidates(cands, limit=5)) == 1


def test_topic_cap_drops_third_without_signal():
    cands = [
        _c("A1", topic="x"),
        _c("A2", topic="x", match_score=5.0, difference_point="d"),
        _c("A3", topic="x"),
    ]
    assert [c["title"] for c in _dedupe_briefing_candidates(cands, limit=5)] == ["A1", "A2"]
