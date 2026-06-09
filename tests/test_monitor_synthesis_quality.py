from unittest.mock import patch

from scripts.monitor_synthesis_quality import _is_fallback_provider, build_report, evaluate_report


class TestMonitorSynthesisQuality:
    def test_is_fallback_provider(self):
        assert _is_fallback_provider("enhanced_fallback") is True
        assert _is_fallback_provider("local") is True
        assert _is_fallback_provider("NULL") is True
        assert _is_fallback_provider("mistral_small") is False

    @patch("scripts.monitor_synthesis_quality._provider_counts")
    @patch("scripts.monitor_synthesis_quality._fallback_reason_counts")
    def test_build_report_computes_ratio(self, mock_reasons, mock_counts):
        mock_counts.return_value = {
            "enhanced_fallback": 30,
            "mistral_small": 70,
        }
        mock_reasons.return_value = {"backfill_enhanced_fallback": 20}

        report = build_report(7)

        assert report["total_summaries"] == 100
        assert report["fallback_total"] == 30
        assert report["fallback_ratio"] == 0.3
        assert report["providers"]["mistral_small"] == 70

    def test_evaluate_report_warn_and_critical(self):
        base = {"window_days": 7, "providers": {"enhanced_fallback": 1}, "top_fallback_reasons": {}}
        warn_report = {**base, "total_summaries": 100, "fallback_total": 40, "fallback_ratio": 0.4}
        critical_report = {**base, "total_summaries": 100, "fallback_total": 60, "fallback_ratio": 0.6}
        healthy_report = {**base, "total_summaries": 100, "fallback_total": 10, "fallback_ratio": 0.1}

        assert evaluate_report(warn_report, 0.35, 0.55) == 1
        assert evaluate_report(critical_report, 0.35, 0.55) == 2
        assert evaluate_report(healthy_report, 0.35, 0.55) == 0
