from unittest.mock import patch

from scripts.monitor_synthesis_quality import (
    _is_fallback_provider,
    build_report,
    build_snapshot,
    evaluate_report,
    evaluate_snapshot,
)


class TestMonitorSynthesisQuality:
    def test_is_fallback_provider(self):
        assert _is_fallback_provider("enhanced_fallback") is True
        assert _is_fallback_provider("local") is True
        assert _is_fallback_provider("NULL") is False
        assert _is_fallback_provider("nvidia") is False

    @patch("scripts.monitor_synthesis_quality._provider_counts")
    @patch("scripts.monitor_synthesis_quality._fallback_reason_counts")
    def test_build_report_computes_ratio(self, mock_reasons, mock_counts):
        mock_counts.return_value = {
            "NULL": 50,
            "enhanced_fallback": 30,
            "nvidia": 70,
        }
        mock_reasons.return_value = {"backfill_enhanced_fallback": 20}

        report = build_report(7)

        assert report["total_summaries"] == 150
        assert report["fallback_total"] == 30
        assert report["legacy_unknown_total"] == 50
        assert report["fallback_ratio"] == 0.2
        assert report["providers"]["nvidia"] == 70

    @patch(
        "scripts.monitor_synthesis_quality._persist_gap_metrics",
        return_value={"synthesis_events": 0, "db_persisted_events": 0, "persist_gap": 0},
    )
    @patch("scripts.monitor_synthesis_quality._runtime_fallback_reason_counts", return_value={})
    @patch("core.synthesis_quality.count_low_score_syntheses", return_value=0)
    @patch(
        "core.synthesis_quality.count_upgradeable_syntheses",
        return_value={"provisional_count": 0, "fallback_count": 0},
    )
    @patch("core.synthesis_quality.count_stuck_fast_syntheses", return_value=0)
    @patch(
        "scripts.monitor_synthesis_quality._unsummarized_counts",
        return_value={"unsummarized_total": 60100, "unsummarized_24h": 847},
    )
    @patch("scripts.monitor_synthesis_quality._synthesis_ops_queue_depth", return_value=160)
    @patch("scripts.monitor_synthesis_quality.build_report")
    def test_build_snapshot_marks_warn_on_queue(
        self,
        mock_build_report,
        _mock_depth,
        _mock_unsummarized,
        _mock_stuck_fast,
        _mock_upgradeable,
        _mock_low_score,
        _mock_runtime_reasons,
        _mock_persist_gap,
    ):
        mock_build_report.side_effect = [
            {"window_days": 1, "total_summaries": 100, "fallback_total": 10, "fallback_ratio": 0.1, "providers": {}},
            {"window_days": 7, "total_summaries": 1000, "fallback_total": 400, "fallback_ratio": 0.4, "providers": {}},
        ]

        snapshot = build_snapshot()

        assert snapshot["status"] == "warn"
        assert snapshot["celery_queue_depth"] == 160
        assert snapshot["unsummarized_total"] == 60100
        assert snapshot["unsummarized_24h"] == 847
        assert snapshot["primary"]["fallback_ratio"] == 0.1

    @patch(
        "scripts.monitor_synthesis_quality._persist_gap_metrics",
        return_value={"synthesis_events": 0, "db_persisted_events": 0, "persist_gap": 0},
    )
    @patch("scripts.monitor_synthesis_quality._runtime_fallback_reason_counts", return_value={})
    @patch("core.synthesis_quality.count_low_score_syntheses", return_value=0)
    @patch(
        "core.synthesis_quality.count_upgradeable_syntheses",
        return_value={"provisional_count": 0, "fallback_count": 0},
    )
    @patch("core.synthesis_quality.count_stuck_fast_syntheses", return_value=14)
    @patch(
        "scripts.monitor_synthesis_quality._unsummarized_counts",
        return_value={"unsummarized_total": 0, "unsummarized_24h": 0},
    )
    @patch("scripts.monitor_synthesis_quality._synthesis_ops_queue_depth", return_value=0)
    @patch("scripts.monitor_synthesis_quality.build_report")
    def test_build_snapshot_warns_on_small_stuck_fast_backlog(
        self,
        mock_build_report,
        _mock_depth,
        _mock_unsummarized,
        _mock_stuck_fast,
        _mock_upgradeable,
        _mock_low_score,
        _mock_runtime_reasons,
        _mock_persist_gap,
    ):
        mock_build_report.side_effect = [
            {"window_days": 1, "total_summaries": 100, "fallback_total": 10, "fallback_ratio": 0.1, "providers": {}},
            {"window_days": 7, "total_summaries": 1000, "fallback_total": 100, "fallback_ratio": 0.1, "providers": {}},
        ]

        snapshot = build_snapshot()

        assert snapshot["status"] == "warn"
        assert snapshot["stuck_fast_synthesis_count"] == 14

    def test_evaluate_report_warn_and_critical(self):
        base = {
            "window_days": 1,
            "providers": {"enhanced_fallback": 1},
            "top_fallback_reasons": {},
            "legacy_unknown_total": 0,
        }
        warn_report = {**base, "total_summaries": 100, "fallback_total": 40, "fallback_ratio": 0.4}
        critical_report = {**base, "total_summaries": 100, "fallback_total": 60, "fallback_ratio": 0.6}
        healthy_report = {**base, "total_summaries": 100, "fallback_total": 10, "fallback_ratio": 0.1}

        assert evaluate_report(warn_report, 0.35, 0.55) == 1
        assert evaluate_report(critical_report, 0.35, 0.55) == 2
        assert evaluate_report(healthy_report, 0.35, 0.55) == 0

    def test_evaluate_snapshot_flags_queue_backlog(self):
        snapshot = {
            "primary": {
                "window_days": 1,
                "total_summaries": 100,
                "fallback_total": 10,
                "fallback_ratio": 0.1,
                "providers": {},
                "top_fallback_reasons": {},
                "legacy_unknown_total": 0,
            },
            "celery_queue_depth": 600,
        }

        assert evaluate_snapshot(snapshot, 0.35, 0.55) == 2
