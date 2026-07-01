from unittest.mock import patch

from tasks.intelligence.synthesis_persist import finalize_cluster_synthesis, persist_lang_synthesis


def test_persist_lang_synthesis_writes_summary_row():
    shared_metrics = {
        "pulse_score": 50,
        "pluralism_score": 20,
        "pluralism_data": {},
        "citation_sources": [],
        "analyst_entities": [],
        "sentiment_data": {},
        "story_so_far": "",
        "centroid_str": None,
        "deep_metadata": {},
    }
    with (
        patch("tasks.intelligence.synthesis_persist.db") as mock_db,
        patch("core.synthesis_quality.record_synthesis_db_persisted"),
        patch("core.synthesis_quality.clear_fast_synthesis_pending"),
        patch("tasks.intelligence.synthesis_persist._schedule_deep_analyst_work"),
        patch("core.audio_service.AudioService.generate_cluster_audio"),
    ):
        result = persist_lang_synthesis(
            cluster_id="c-1",
            lang="sr",
            article_rows=[{"source": "RTS", "title": "Vest"}],
            cascade={"status": "success"},
            res_data={"key_facts": ["RTS: Vest"], "tone_analysis": {}},
            summary="Sažetak",
            generated_article="Članak",
            synthetic_headline="Naslov",
            synthetic_standfirst="",
            perspectives=[{"angle": "Razlika", "content": "Tekst"}],
            verification_report=None,
            quote="",
            shared_metrics=shared_metrics,
            provider="local",
            model="gemma",
            quality_score=0.8,
            fallback_reason=None,
            fast_mode=False,
            current_impact_score=0.0,
            current_impact_reasoning="",
            current_story_so_far="",
            current_sentiment_data={},
            shared_computed=False,
        )

    assert result["synthesis_persisted"] is True
    assert mock_db.execute.call_count >= 2


def test_finalize_cluster_synthesis_skips_when_nothing_persisted():
    with patch("tasks.intelligence.synthesis_persist.db") as mock_db:
        finalize_cluster_synthesis(
            cluster_id="c-1",
            article_rows=[],
            shared_metrics={"impact_score": 0.0, "impact_reasoning": ""},
            synthesis_persisted=False,
            shared_computed=False,
        )
    mock_db.execute.assert_not_called()
