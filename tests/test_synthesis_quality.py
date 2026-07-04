from core.synthesis_quality import build_synthesis_meta, synthesis_needs_upgrade, synthesis_quality_threshold


def test_synthesis_quality_threshold_by_provider():
    assert synthesis_quality_threshold("local") == 0.65
    assert synthesis_quality_threshold("nvidia") == 0.70
    assert synthesis_quality_threshold("unknown_provider") == 0.70


def test_synthesis_quality_threshold_skipped_in_fast_mode():
    assert synthesis_quality_threshold("nvidia", fast_mode=True) is None


def test_order_synthesis_langs_sr_first():
    langs = list(dict.fromkeys(["mk", "sr"]))
    ordered = ["sr", "mk"] if "sr" in langs and "mk" in langs else langs
    assert ordered == ["sr", "mk"]
    assert list(dict.fromkeys(["mk"])) == ["mk"]


def test_synthesis_needs_upgrade():
    assert synthesis_needs_upgrade("fast_mode_provisional", "nvidia") is True
    assert synthesis_needs_upgrade(None, "enhanced_fallback") is True
    assert synthesis_needs_upgrade("quality_gate_failed_enhanced_fallback", None) is True
    assert synthesis_needs_upgrade(None, "nvidia") is False


def test_fact_grounding_diagnostics_reports_ungrounded_numbers():
    from tasks.intelligence.synthesis_grounding import _fact_grounding_diagnostics

    articles = [{"title": "Vest", "description": "Cena je 100 dinara.", "full_content": ""}]
    diagnostics = _fact_grounding_diagnostics(
        "Investicija iznosi 987654 dinara, 876543 evra i rast od 77, 66 i 55 procenata.",
        articles,
        lang="sr",
    )
    assert diagnostics["ok"] is False
    assert diagnostics["ungrounded_numbers"]


def test_build_synthesis_meta():
    meta = build_synthesis_meta(
        {
            "generation_provider": "nvidia",
            "generation_model": "nvidia-latest",
            "quality_score": 0.82,
            "fallback_reason": "fast_mode_provisional",
        },
        lang="sr",
    )
    assert meta["is_provisional"] is True
    assert meta["needs_upgrade"] is True
    assert meta["generation_model"] == "nvidia-latest"


def test_count_synthesis_persist_gap(monkeypatch):
    from core.synthesis_quality import count_synthesis_persist_gap

    class _FakeRedis:
        def hgetall(self, _key):
            return {
                "synthesis_path|lang=sr|mode=nvidia": 3,
                "synthesis_path|lang=sr|mode=enhanced_fallback|reason=router_empty_articles": 2,
                "synthesis_db_persisted|lang=sr|mode=nvidia": 1,
            }

    monkeypatch.setattr("utils.redis_client", _FakeRedis())
    metrics = count_synthesis_persist_gap()
    assert metrics["synthesis_events"] == 3
    assert metrics["excluded_synthesis_events"] == 2
    assert metrics["db_persisted_events"] == 1
    assert metrics["persist_gap"] == 2


def test_record_synthesis_db_persisted(monkeypatch):
    from core.synthesis_quality import record_synthesis_db_persisted

    events = []

    def _record(event, **fields):
        events.append((event, fields))

    monkeypatch.setattr("utils.record_runtime_event", _record)
    record_synthesis_db_persisted(
        cluster_id="abc123",
        lang="sr",
        provider="nvidia",
        fast_mode=False,
    )
    assert events[0][0] == "synthesis_db_persisted"
    assert events[0][1]["cluster_id"] == "abc123"


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
