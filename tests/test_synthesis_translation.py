from unittest.mock import patch

from tasks.intelligence.synthesis_translation import try_translate_synthesis_to_mk


def test_translate_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr("core.limits.SYNTHESIS_MK_TRANSLATE_FROM_SR", False)
    result = try_translate_synthesis_to_mk({"synthetic_headline": "Test"}, [])
    assert result is None


def test_translate_returns_none_for_empty_bundle():
    assert try_translate_synthesis_to_mk(None, []) is None


def test_translate_success_path(monkeypatch):
    monkeypatch.setenv("SYNTHESIS_MK_TRANSLATE_FROM_SR", "true")
    sr_bundle = {
        "synthetic_headline": "Vlada usvojila izmene",
        "summary": "- Šta: izmene",
        "generated_article": "Vlada je usvojila izmene zakona.",
        "quality_score": 0.8,
    }
    article_rows = [{"title": "Vlada usvojila izmene", "description": "Izmene", "source": "RTS"}]
    trans_data = {
        "synthetic_headline": "Владата усвои измени",
        "summary": "- Што: измени",
        "article": "Владата усвои измени на законот според извештаите на МРТ.",
    }

    with patch("tasks.intelligence.synthesis_translation._call_ai", return_value=('{"ok":true}', "nvidia")):
        with patch("tasks.intelligence.synthesis_translation.clean_json_response", return_value=trans_data):
            with patch("tasks.intelligence.synthesis_translation._is_fact_grounded_synthesis", return_value=True):
                with patch("core.copy_quality.copy_bundle_passes_publish_gate", return_value=(True, {})):
                    result = try_translate_synthesis_to_mk(sr_bundle, article_rows, fast_mode=True)

    assert result is not None
    assert result["fallback_reason"] == "translated_from_sr"
    assert result["res_data"]["synthetic_headline"] == "Владата усвои измени"
