from core.synthesis_quality import build_synthesis_meta, synthesis_needs_upgrade, synthesis_quality_threshold


def test_synthesis_quality_threshold_by_provider():
    assert synthesis_quality_threshold("local") == 0.65
    assert synthesis_quality_threshold("mistral_small") == 0.70
    assert synthesis_quality_threshold("mistral_large") == 0.75
    assert synthesis_quality_threshold("nvidia") == 0.70


def test_synthesis_quality_threshold_skipped_in_fast_mode():
    assert synthesis_quality_threshold("mistral_small", fast_mode=True) is None


def test_order_synthesis_langs_sr_first():
    from tasks.intelligence.synthesis import _order_synthesis_langs

    assert _order_synthesis_langs(["mk", "sr"]) == ["sr", "mk"]
    assert _order_synthesis_langs(["mk"]) == ["mk"]


def test_synthesis_needs_upgrade():
    assert synthesis_needs_upgrade("fast_mode_provisional", "mistral_small") is True
    assert synthesis_needs_upgrade(None, "enhanced_fallback") is True
    assert synthesis_needs_upgrade("quality_gate_failed_enhanced_fallback", None) is True
    assert synthesis_needs_upgrade(None, "mistral_small") is False


def test_build_synthesis_meta():
    meta = build_synthesis_meta(
        {
            "generation_provider": "mistral_small",
            "generation_model": "mistral-small-latest",
            "quality_score": 0.82,
            "fallback_reason": "fast_mode_provisional",
        },
        lang="sr",
    )
    assert meta["is_provisional"] is True
    assert meta["needs_upgrade"] is True
    assert meta["generation_model"] == "mistral-small-latest"


def test_list_stuck_fast_synthesis_cluster_ids(monkeypatch):
    from core.synthesis_quality import list_stuck_fast_synthesis_cluster_ids

    class FakeRedis:
        def scan_iter(self, pattern, count=200):
            return iter(["presek:fast_synthesis_pending:cluster-a", "presek:fast_synthesis_pending:cluster-b"])

        def ttl(self, key):
            return 3600 if key.endswith("cluster-a") else 100000

    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("FAST_SYNTHESIS_PENDING_TTL_SECONDS", "172800")
    monkeypatch.setattr("utils.redis_client", FakeRedis())

    stuck = list_stuck_fast_synthesis_cluster_ids(max_age_hours=24, limit=10)
    assert stuck == ["cluster-a"]
