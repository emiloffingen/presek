import json
from pathlib import Path
from unittest.mock import patch

from tasks.intelligence.synthesis_pipeline import run_cluster_synthesis


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "synthesis_pipeline_sample.json"


def _load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_run_cluster_synthesis_persists_successful_sr_cascade():
    fixture = _load_fixture()
    cascade = fixture["cascade_success"]
    articles = fixture["article_rows"]

    with (
        patch(
            "tasks.intelligence.synthesis_pipeline._load_cluster_articles_for_synthesis",
            return_value=articles,
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._fetch_synthesis_history_context",
            return_value="",
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._build_source_comparison_prompt_block",
            return_value="",
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._generate_synthesis_via_cascade",
            return_value=cascade,
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._sanitize_synthesis_outputs",
            side_effect=lambda summary, article, perspectives, *_args, **_kwargs: (
                summary,
                article,
                perspectives,
            ),
        ),
        patch("core.copy_quality.copy_bundle_passes_publish_gate", return_value=(True, {})),
        patch("core.synthesis_quality.record_synthesis_runtime_event"),
        patch(
            "tasks.intelligence.synthesis_pipeline.persist_lang_synthesis",
            return_value={
                "synthesis_persisted": True,
                "fast_synthesis_succeeded": False,
                "shared_computed": True,
            },
        ) as mock_persist,
        patch("tasks.intelligence.synthesis_pipeline.finalize_cluster_synthesis") as mock_finalize,
        patch("core.llm_router.SmartModelRouter._record_quality_feedback"),
    ):
        run_cluster_synthesis(fixture["cluster_id"], "", fast_mode=False)

    mock_persist.assert_called_once()
    assert mock_persist.call_args.kwargs["lang"] == "sr"
    mock_finalize.assert_called_once()
    assert mock_finalize.call_args.kwargs["synthesis_persisted"] is True


def test_run_cluster_synthesis_schedules_fast_upgrade_on_fast_mode():
    fixture = _load_fixture()
    cascade = {**fixture["cascade_success"], "fallback_reason": "fast_mode_provisional"}

    with (
        patch(
            "tasks.intelligence.synthesis_pipeline._load_cluster_articles_for_synthesis",
            return_value=fixture["article_rows"],
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._generate_synthesis_via_cascade",
            return_value=cascade,
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._sanitize_synthesis_outputs",
            side_effect=lambda summary, article, perspectives, *_args, **_kwargs: (
                summary,
                article,
                perspectives,
            ),
        ),
        patch(
            "core.copy_quality.copy_bundle_passes_publish_gate",
            return_value=(True, {}),
        ),
        patch("core.synthesis_quality.record_synthesis_runtime_event"),
        patch(
            "tasks.intelligence.synthesis_pipeline.persist_lang_synthesis",
            return_value={
                "synthesis_persisted": True,
                "fast_synthesis_succeeded": True,
                "shared_computed": False,
            },
        ),
        patch("tasks.intelligence.synthesis_pipeline.finalize_cluster_synthesis"),
        patch(
            "tasks.intelligence.synthesis_pipeline._schedule_fast_synthesis_upgrade",
            return_value=True,
        ) as mock_upgrade,
    ):
        run_cluster_synthesis(fixture["cluster_id"], "legacy", fast_mode=True)

    mock_upgrade.assert_called_once_with(fixture["cluster_id"], "legacy")


def test_run_cluster_synthesis_schedules_copy_purity_retry_when_gate_fails():
    fixture = _load_fixture()
    cascade = fixture["cascade_success"]

    with (
        patch(
            "tasks.intelligence.synthesis_pipeline._load_cluster_articles_for_synthesis",
            return_value=fixture["article_rows"],
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._generate_synthesis_via_cascade",
            return_value=cascade,
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._sanitize_synthesis_outputs",
            side_effect=lambda summary, article, perspectives, *_args, **_kwargs: (
                summary,
                article,
                perspectives,
            ),
        ),
        patch(
            "core.copy_quality.copy_bundle_passes_publish_gate",
            return_value=(False, {"reason": "sr_leak"}),
        ),
        patch("core.synthesis_quality.record_synthesis_runtime_event"),
        patch("tasks.intelligence.synthesis_pipeline.persist_lang_synthesis") as mock_persist,
        patch("tasks.intelligence.synthesis_pipeline.finalize_cluster_synthesis") as mock_finalize,
        patch(
            "tasks.intelligence.synthesis_pipeline._schedule_copy_purity_retry",
        ) as mock_retry,
    ):
        run_cluster_synthesis(fixture["cluster_id"], "", fast_mode=False)

    mock_retry.assert_called_once_with(fixture["cluster_id"], "", lang="sr", fast_mode=False)
    mock_persist.assert_not_called()
    mock_finalize.assert_called_once()
    assert mock_finalize.call_args.kwargs["synthesis_persisted"] is False


def test_run_cluster_synthesis_uses_enhanced_fallback_when_cascade_exhausted():
    fixture = _load_fixture()
    exhausted = {
        "status": "exhausted",
        "provider": None,
        "model": None,
        "quality_score": None,
        "fallback_reason": "all_providers_failed",
        "cascade_depth": 3,
        "raw": "",
        "res_data": {},
    }
    fallback_payload = {
        "summary": "- Fallback rezime",
        "perspectives": [{"angle": "Fallback", "content": "Fallback perspektiva."}],
        "synthetic_headline": "Fallback naslov",
        "synthetic_standfirst": "",
        "generated_article": "Fallback članak sa dovoljno teksta za publish gate.",
    }

    with (
        patch(
            "tasks.intelligence.synthesis_pipeline._load_cluster_articles_for_synthesis",
            return_value=fixture["article_rows"],
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline._generate_synthesis_via_cascade",
            return_value=exhausted,
        ),
        patch(
            "tasks.intelligence.synthesis_pipeline.synthesize_cluster_fallback",
            return_value=fallback_payload,
        ) as mock_fallback,
        patch(
            "tasks.intelligence.synthesis_pipeline._sanitize_synthesis_outputs",
            side_effect=lambda summary, article, perspectives, *_args, **_kwargs: (
                summary,
                article,
                perspectives,
            ),
        ),
        patch("core.copy_quality.copy_bundle_passes_publish_gate", return_value=(True, {})),
        patch("core.synthesis_quality.record_synthesis_runtime_event"),
        patch(
            "tasks.intelligence.synthesis_pipeline.persist_lang_synthesis",
            return_value={
                "synthesis_persisted": True,
                "fast_synthesis_succeeded": False,
                "shared_computed": True,
            },
        ) as mock_persist,
        patch("tasks.intelligence.synthesis_pipeline.finalize_cluster_synthesis"),
    ):
        run_cluster_synthesis(fixture["cluster_id"], "", fast_mode=False)

    mock_fallback.assert_called_once_with(fixture["article_rows"], lang="sr")
    mock_persist.assert_called_once()
    assert mock_persist.call_args.kwargs["provider"] == "enhanced_fallback"
