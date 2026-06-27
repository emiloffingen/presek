"""Cluster synthesis generation loop and orchestration."""

from __future__ import annotations

from core.entities import validate_person_names
from core.prompts import SYNTHESIS_SYSTEM_PROMPT_MK, SYNTHESIS_SYSTEM_PROMPT_SR
from nlp import synthesize_cluster_fallback
from tasks.synthesis_sanitize import sanitize_synthesis_outputs as _sanitize_synthesis_outputs
from tasks.intelligence.synthesis_generation import _generate_synthesis_via_cascade
from tasks.intelligence.synthesis_bundle import (
    _build_citation_sources,
    _build_synthesis_source_context,
    _ensure_dict,
)
from tasks.intelligence.synthesis_persist import finalize_cluster_synthesis, persist_lang_synthesis
from tasks.intelligence.synthesis_prompt import (
    _build_source_comparison_prompt_block,
    _fetch_synthesis_history_context,
    _langs_for_cluster_articles,
    _load_cluster_articles_for_synthesis,
    _order_synthesis_langs,
)
from tasks.intelligence.synthesis_scheduling import (
    _schedule_copy_purity_retry,
    _schedule_fast_synthesis_upgrade,
)
from tasks.intelligence.synthesis_scoring import _compute_lightweight_quality_score
from tasks.intelligence.synthesis_translation import try_translate_synthesis_to_mk as _try_translate_synthesis_to_mk
from tasks.utils import log


def run_cluster_synthesis(cluster_id, content, fast_mode=False, force_llm=False):
    """Generates a multi-perspective synthesis for a cluster with historical continuity."""
    from core.synthesis_quality import record_synthesis_runtime_event

    article_rows = _load_cluster_articles_for_synthesis(cluster_id)
    citation_sources = _build_citation_sources(article_rows)
    target_langs = _order_synthesis_langs(_langs_for_cluster_articles(article_rows))
    source_context_sr = _build_synthesis_source_context(article_rows, lang="sr")
    source_context_mk = _build_synthesis_source_context(article_rows, lang="mk")

    # Non-fast synthesis needs room for a longer editorial article plus the surrounding JSON fields.
    max_tokens = 2200 if fast_mode else 5200

    legacy_summary = str(content or "").strip()

    # Track shared metrics that only need to be computed once per cluster
    shared_metrics = {
        "impact_score": 0.0,
        "impact_reasoning": "",
        "story_so_far": "",
        "centroid_str": None,
        "deep_metadata": {},
        "pluralism_data": {},
        "sentiment_data": {"sentiment": {"score": 0, "tone": "neutralan"}, "tone_analysis": {}},
        "citation_sources": citation_sources,
        "pulse_score": 50,
        "pluralism_score": 50,
        "analyst_entities": [],
    }
    shared_computed = False
    fast_synthesis_succeeded = False
    synthesis_persisted = False
    sr_success_bundle = None

    for lang in target_langs:
        current_impact_score = 0.0
        current_impact_reasoning = ""
        current_story_so_far = ""
        current_sentiment_data = shared_metrics["sentiment_data"]
        try:
            log.info(f"Generating synthesis for cluster {cluster_id} in {lang}")

            if lang == "mk" and sr_success_bundle:
                translated = _try_translate_synthesis_to_mk(sr_success_bundle, article_rows, fast_mode=fast_mode)
                if translated and translated.get("status") == "success":
                    cascade = translated
                else:
                    cascade = None
            else:
                cascade = None

            if cascade is None:
                prompt_parts = []
                if fast_mode:
                    prompt_parts.append(
                        "FAST MODE: return the full valid JSON schema, but keep the editorial article concise and complete "
                        "(350-500 words). Include the core event, context, source comparison, consequences, and one clear "
                        "open question. Do not reduce the article to a single paragraph."
                    )
                else:
                    history_context = _fetch_synthesis_history_context(cluster_id, lang=lang, article_rows=article_rows)
                    if history_context:
                        prompt_parts.append(history_context)

                source_comparison = _build_source_comparison_prompt_block(article_rows, lang=lang)
                if source_comparison:
                    prompt_parts.append(source_comparison)

                prompt_parts.append("novi clanci OD danas:\n<articles_context>")
                current_context = source_context_mk if lang == "mk" else source_context_sr
                if current_context:
                    prompt_parts.append(current_context)
                elif legacy_summary:
                    prompt_parts.append(legacy_summary)
                prompt_parts.append("</articles_context>")
                if lang == "mk":
                    prompt_parts.append(
                        "УРЕДНИЧКИ ФОКУС: резимето не смее да биде список на наслови. "
                        "Изведи 3-4 паметни точки: нов развој, зошто е важен, што навистина е потврдено "
                        "и што останува непознато или следно за проверка."
                    )
                else:
                    prompt_parts.append(
                        "UREĐIVAČKI FOKUS: rezime ne sme biti lista naslova. "
                        "Izvedi 3-4 pametne tačke: novi razvoj, zašto je važan, šta je zaista potvrđeno "
                        "i šta ostaje nepoznato ili sledeće za proveru."
                    )
                full_prompt = "\n\n".join(part for part in prompt_parts if part)

                system_prompt = SYNTHESIS_SYSTEM_PROMPT_MK if lang == "mk" else SYNTHESIS_SYSTEM_PROMPT_SR

                cascade = _generate_synthesis_via_cascade(
                    article_rows,
                    full_prompt,
                    system_prompt,
                    lang=lang,
                    max_tokens=max_tokens,
                    fast_mode=fast_mode,
                    current_context=current_context,
                    legacy_summary=legacy_summary,
                    force_llm=force_llm,
                )
            else:
                current_context = source_context_mk if lang == "mk" else source_context_sr

            provider = cascade.get("provider")
            model = cascade.get("model")
            quality_score = cascade.get("quality_score")
            fallback_reason = cascade.get("fallback_reason")
            if cascade.get("status") == "success":
                if fast_mode:
                    fallback_reason = fallback_reason or "fast_mode_provisional"
                elif fallback_reason == "fast_mode_provisional":
                    fallback_reason = None
            raw = cascade.get("raw")
            res_data = cascade.get("res_data") or {}

            if cascade["status"] == "success":
                summary = res_data.get("summary", "")
                generated_article = res_data.get("article", "") or res_data.get("generated_article", "")
                synthetic_headline = res_data.get("synthetic_headline", "")
                synthetic_standfirst = res_data.get("synthetic_standfirst", "")
                perspectives = res_data.get("perspectives", [])
                if isinstance(summary, list):
                    summary = "\n".join(str(s) for s in summary)

                verification_report = res_data.get("verification_report")
                quote = validate_person_names(res_data.get("quote", ""))

                # Sanitize for name hallucinations
                summary = validate_person_names(summary)
                generated_article = validate_person_names(generated_article)
                synthetic_headline = validate_person_names(synthetic_headline)
                synthetic_standfirst = validate_person_names(synthetic_standfirst)

                # --- [NEW] 2026 Intelligence: Storyline & Impact ---
                current_story_so_far = validate_person_names(res_data.get("story_so_far", ""))
                impact_data = _ensure_dict(res_data.get("impact_analysis", {}))
                current_impact_score = float(impact_data.get("score", 0.0))
                current_impact_reasoning = impact_data.get("reasoning", "")

                current_sentiment_data = {
                    "sentiment": res_data.get("sentiment", {}),
                    "tone_analysis": res_data.get("tone_analysis", {}),
                }

                summary, generated_article, perspectives = _sanitize_synthesis_outputs(
                    summary,
                    generated_article,
                    perspectives,
                    article_rows,
                    lang=lang,
                )
                if fast_mode:
                    if quality_score is None:
                        quality_score = _compute_lightweight_quality_score(
                            synthetic_headline,
                            summary,
                            generated_article,
                            res_data.get("key_facts", []),
                            lang=lang,
                        )
                record_synthesis_runtime_event(
                    provider=provider or "unknown",
                    lang=lang,
                    fast_mode=fast_mode,
                    fallback_reason=fallback_reason,
                    cascade_depth=cascade.get("cascade_depth"),
                )
                
                if provider and quality_score is not None:
                    from core.llm_router import SmartModelRouter

                    SmartModelRouter._record_quality_feedback(provider, cluster_id, quality_score)

                if lang == "sr" and cascade["status"] == "success":
                    sr_success_bundle = {
                        "synthetic_headline": synthetic_headline,
                        "synthetic_standfirst": synthetic_standfirst,
                        "summary": summary,
                        "generated_article": generated_article,
                        "key_facts": res_data.get("key_facts", []),
                        "perspectives": perspectives,
                        "verification_report": verification_report,
                        "sentiment": res_data.get("sentiment", {}),
                        "tone_analysis": res_data.get("tone_analysis", {}),
                        "story_so_far": current_story_so_far,
                        "impact_analysis": impact_data,
                        "quote": quote,
                        "quality_score": quality_score,
                    }

            else:
                if cascade["status"] == "deterministic":
                    log.info(f"Using deterministic enhanced fallback for {cluster_id} ({lang})")
                else:
                    log.warning(
                        f"[tasks/synthesis] Provider cascade exhausted for {cluster_id} ({lang}); "
                        f"reason={fallback_reason}"
                    )
                provider = "enhanced_fallback"
                model = "enhanced_fallback"
                fallback_reason = fallback_reason or "enhanced_fallback_after_cascade_exhausted"
                fallback = synthesize_cluster_fallback(article_rows, lang=lang)
                summary = fallback.get("summary", "")
                perspectives = fallback.get("perspectives", [])
                synthetic_headline = fallback.get("synthetic_headline", "")
                synthetic_standfirst = fallback.get("synthetic_standfirst", "")
                generated_article = fallback.get("generated_article", "")
                record_synthesis_runtime_event(
                    provider=provider,
                    lang=lang,
                    fast_mode=fast_mode,
                    fallback_reason=fallback_reason,
                    cascade_depth=cascade.get("cascade_depth"),
                )
                verification_report = None
                quote = ""
                current_sentiment_data = shared_metrics["sentiment_data"]

                if not shared_computed:
                    shared_metrics["impact_score"] = 0.0
                    shared_metrics["impact_reasoning"] = ""
                    shared_metrics["story_so_far"] = ""
                    shared_computed = True  # Mark as computed even if fallback

            summary, generated_article, perspectives = _sanitize_synthesis_outputs(
                summary,
                generated_article,
                perspectives,
                article_rows,
                lang=lang,
            )

            if lang == "mk" and (summary or generated_article):
                from core.copy_quality import copy_bundle_passes_publish_gate

                copy_ok, copy_diag = copy_bundle_passes_publish_gate(
                    lang="mk",
                    headline=synthetic_headline,
                    summary=summary,
                    article=generated_article,
                    key_facts=res_data.get("key_facts", []) if cascade.get("status") == "success" else [],
                )
                if not copy_ok:
                    log.warning(
                        "[tasks/synthesis] MK publish blocked after sanitize for %s: %s",
                        cluster_id,
                        copy_diag,
                    )
                    record_synthesis_runtime_event(
                        provider=provider or "unknown",
                        lang=lang,
                        fast_mode=fast_mode,
                        fallback_reason="mk_copy_purity_failed",
                        cascade_depth=cascade.get("cascade_depth"),
                    )
                    _schedule_copy_purity_retry(cluster_id, legacy_summary, lang=lang, fast_mode=fast_mode)
                    continue
            elif lang == "sr" and (summary or generated_article):
                from core.copy_quality import copy_bundle_passes_publish_gate

                copy_ok, copy_diag = copy_bundle_passes_publish_gate(
                    lang="sr",
                    headline=synthetic_headline,
                    summary=summary,
                    article=generated_article,
                    key_facts=res_data.get("key_facts", []) if cascade.get("status") == "success" else [],
                )
                if not copy_ok:
                    log.warning(
                        "[tasks/synthesis] SR publish blocked after sanitize for %s: %s",
                        cluster_id,
                        copy_diag,
                    )
                    record_synthesis_runtime_event(
                        provider=provider or "unknown",
                        lang=lang,
                        fast_mode=fast_mode,
                        fallback_reason="sr_copy_purity_failed",
                        cascade_depth=cascade.get("cascade_depth"),
                    )
                    _schedule_copy_purity_retry(cluster_id, legacy_summary, lang=lang, fast_mode=fast_mode)
                    continue

            if summary or perspectives:
                persist_result = persist_lang_synthesis(
                    cluster_id=cluster_id,
                    lang=lang,
                    article_rows=article_rows,
                    cascade=cascade,
                    res_data=res_data,
                    summary=summary,
                    generated_article=generated_article,
                    synthetic_headline=synthetic_headline,
                    synthetic_standfirst=synthetic_standfirst,
                    perspectives=perspectives,
                    verification_report=verification_report,
                    quote=quote,
                    shared_metrics=shared_metrics,
                    provider=provider,
                    model=model,
                    quality_score=quality_score,
                    fallback_reason=fallback_reason,
                    fast_mode=fast_mode,
                    current_impact_score=current_impact_score,
                    current_impact_reasoning=current_impact_reasoning,
                    current_story_so_far=current_story_so_far,
                    current_sentiment_data=current_sentiment_data,
                    shared_computed=shared_computed,
                )
                synthesis_persisted = synthesis_persisted or persist_result["synthesis_persisted"]
                fast_synthesis_succeeded = fast_synthesis_succeeded or persist_result["fast_synthesis_succeeded"]
                shared_computed = persist_result["shared_computed"]

        except Exception as e:
            log.error(f"Synthesis failed for cluster {cluster_id} in {lang}: {e}", exc_info=True)
            continue

    if fast_mode and fast_synthesis_succeeded:
        _schedule_fast_synthesis_upgrade(cluster_id, legacy_summary or None)

    finalize_cluster_synthesis(
        cluster_id=cluster_id,
        article_rows=article_rows,
        shared_metrics=shared_metrics,
        synthesis_persisted=synthesis_persisted,
        shared_computed=shared_computed,
    )

