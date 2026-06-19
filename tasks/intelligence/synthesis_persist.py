"""Database persistence and post-synthesis cluster finalization."""

from __future__ import annotations

import datetime
import json
import os

from core.ai_engine import clean_json_response
from nlp import generate_local_placeholder
from tasks.intelligence._constants import (
    STRONG_IMAGE_SQL_FILTER,
    _call_ai,
    db,
    generate_cover_art,
)
from tasks.intelligence.synthesis_bundle import _fallback_key_facts
from tasks.intelligence.synthesis_scheduling import _schedule_deep_analyst_work
from tasks.utils import invalidate_cluster_caches, log


def _translate_key_facts_to_mk(key_facts: list) -> list:
    if not key_facts:
        return key_facts

    facts_text = "\n".join(f"- {fact}" for fact in key_facts)
    translate_prompt = (
        "Преведи ги следните клучни факти од српски (латиница) на чист македонски литературен јазик (кирилица).\n"
        'Врати ги преведените факти како чист JSON од тип {"facts": ["факт 1", "факт 2", ...]} '
        "без никакви дополнителни објаснувања, markdown или воведи.\n\n"
        f"{facts_text}"
    )
    try:
        raw_trans, _ = _call_ai(
            prompt=translate_prompt,
            system="Ти си професионален преведувач за вести од српски на македонски јазик.",
            task_type="translation",
            max_tokens=500,
            json_mode=True,
            lang="mk",
        )
        if not raw_trans:
            return key_facts
        trans_data = clean_json_response(raw_trans)
        if isinstance(trans_data, dict) and trans_data.get("facts"):
            translated_facts = trans_data["facts"]
            if isinstance(translated_facts, list) and len(translated_facts) == len(key_facts):
                log.info("Successfully translated key_facts from Serbian to Macedonian")
                return translated_facts
    except Exception as exc:
        log.warning(f"Failed to translate key_facts to Macedonian: {exc}")
    return key_facts


def persist_lang_synthesis(
    *,
    cluster_id: str,
    lang: str,
    article_rows,
    cascade: dict,
    res_data: dict,
    summary,
    generated_article,
    synthetic_headline,
    synthetic_standfirst,
    perspectives,
    verification_report,
    quote,
    shared_metrics: dict,
    provider,
    model,
    quality_score,
    fallback_reason,
    fast_mode: bool,
    current_impact_score: float,
    current_impact_reasoning: str,
    current_story_so_far: str,
    current_sentiment_data: dict,
    shared_computed: bool,
) -> dict:
    """Archive and upsert one language synthesis row. Returns state updates."""
    from core.synthesis_quality import (
        clear_fast_synthesis_pending,
        mark_fast_synthesis_pending,
        record_synthesis_db_persisted,
    )

    pulse_score = shared_metrics["pulse_score"]
    pluralism_score = shared_metrics["pluralism_score"]
    pluralism_data = shared_metrics["pluralism_data"] or {
        "score": pluralism_score,
        "verdict": "Procenkata e vo tek." if lang == "mk" else "Procena je u toku.",
    }

    key_facts = res_data.get("key_facts")
    if not key_facts or not isinstance(key_facts, list):
        key_facts = shared_metrics["deep_metadata"].get("facts") or _fallback_key_facts(article_rows, summary)

    if lang == "mk" and key_facts:
        key_facts = _translate_key_facts_to_mk(key_facts)

    db.execute(
        """INSERT INTO cluster_summary_history (cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities, generation_provider, generation_model, quality_score, fallback_reason)
           SELECT cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, verification_report, citation_sources, tone_analysis, created_at, key_facts, analyst_entities, generation_provider, generation_model, quality_score, fallback_reason
           FROM cluster_summaries WHERE cluster_id = %s AND lang = %s""",
        (cluster_id, lang),
        fetch=False,
    )

    if res_data.get("full_article_draft") and len(res_data["full_article_draft"]) > 100:
        db.execute(
            """INSERT INTO cluster_summaries (cluster_id, lang, summary, generated_article, synthetic_headline, synthetic_standfirst, created_at, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity, generation_provider, generation_model, quality_score, fallback_reason)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (cluster_id, lang) DO UPDATE SET
                   summary = EXCLUDED.summary,
                   generated_article = EXCLUDED.generated_article,
                   synthetic_headline = EXCLUDED.synthetic_headline,
                   synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                   created_at = EXCLUDED.created_at,
                   citation_sources = EXCLUDED.citation_sources,
                   key_facts = EXCLUDED.key_facts,
                   analyst_entities = EXCLUDED.analyst_entities,
                   pulse_score = EXCLUDED.pulse_score,
                   pluralism_score = EXCLUDED.pluralism_score,
                   narrative_diversity = EXCLUDED.narrative_diversity,
                   generation_provider = EXCLUDED.generation_provider,
                   generation_model = EXCLUDED.generation_model,
                   quality_score = EXCLUDED.quality_score,
                   fallback_reason = EXCLUDED.fallback_reason""",
            (
                cluster_id,
                lang,
                summary,
                generated_article,
                synthetic_headline,
                synthetic_standfirst,
                datetime.datetime.now(),
                json.dumps(shared_metrics["citation_sources"]),
                json.dumps(key_facts),
                json.dumps(shared_metrics["analyst_entities"]),
                float(pulse_score),
                float(pluralism_score),
                json.dumps(pluralism_data),
                provider,
                model,
                quality_score,
                fallback_reason,
            ),
            fetch=False,
        )
    else:
        db.execute(
            """INSERT INTO cluster_summaries (cluster_id, lang, summary, perspectives, generated_article, synthetic_headline, synthetic_standfirst, created_at, sentiment, tone_analysis, verification_report, quote, centroid, citation_sources, key_facts, analyst_entities, pulse_score, pluralism_score, narrative_diversity, storyline_narrative, generation_provider, generation_model, quality_score, fallback_reason)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (cluster_id, lang) DO UPDATE SET
                   summary = EXCLUDED.summary,
                   perspectives = EXCLUDED.perspectives,
                   generated_article = EXCLUDED.generated_article,
                   synthetic_headline = EXCLUDED.synthetic_headline,
                   synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                   created_at = EXCLUDED.created_at,
                   sentiment = EXCLUDED.sentiment,
                   tone_analysis = EXCLUDED.tone_analysis,
                   verification_report = EXCLUDED.verification_report,
                   quote = EXCLUDED.quote,
                   centroid = EXCLUDED.centroid,
                   citation_sources = EXCLUDED.citation_sources,
                   key_facts = EXCLUDED.key_facts,
                   analyst_entities = EXCLUDED.analyst_entities,
                   pulse_score = EXCLUDED.pulse_score,
                   pluralism_score = EXCLUDED.pluralism_score,
                   narrative_diversity = EXCLUDED.narrative_diversity,
                   storyline_narrative = EXCLUDED.storyline_narrative,
                   generation_provider = EXCLUDED.generation_provider,
                   generation_model = EXCLUDED.generation_model,
                   quality_score = EXCLUDED.quality_score,
                   fallback_reason = EXCLUDED.fallback_reason""",
            (
                cluster_id,
                lang,
                summary,
                json.dumps(perspectives),
                generated_article,
                synthetic_headline,
                synthetic_standfirst,
                datetime.datetime.now(),
                json.dumps(shared_metrics["sentiment_data"]),
                json.dumps(res_data.get("tone_analysis", {})),
                (json.dumps(verification_report) if verification_report else None),
                quote,
                shared_metrics["centroid_str"],
                json.dumps(shared_metrics["citation_sources"]),
                json.dumps(key_facts),
                json.dumps(shared_metrics["analyst_entities"]),
                float(pulse_score),
                float(pluralism_score),
                json.dumps(pluralism_data),
                shared_metrics["story_so_far"],
                provider,
                model,
                quality_score,
                fallback_reason,
            ),
            fetch=False,
        )

    log.info(f"Successfully synthesized cluster {cluster_id} for {lang}")
    record_synthesis_db_persisted(
        cluster_id=cluster_id,
        lang=lang,
        provider=provider,
        fast_mode=fast_mode,
    )
    if not fast_mode:
        clear_fast_synthesis_pending(cluster_id)
    else:
        mark_fast_synthesis_pending(cluster_id)

    updated_shared_computed = shared_computed
    if cascade.get("status") == "success" and not fast_mode and not shared_computed:
        _schedule_deep_analyst_work(
            cluster_id=cluster_id,
            article_rows=article_rows,
            lang=lang,
            synthetic_headline=synthetic_headline,
            summary=summary,
            shared_metrics=shared_metrics,
            impact_score=current_impact_score,
            impact_reasoning=current_impact_reasoning,
            story_so_far=current_story_so_far,
            sentiment_data=current_sentiment_data,
        )
        updated_shared_computed = True

    try:
        from core.audio_service import AudioService, select_cluster_audio_text

        audio_content = select_cluster_audio_text(generated_article, summary)
        if audio_content:
            log.info(
                "[tasks] Auto-generating cluster audio in background for cluster %s (%s)...",
                cluster_id,
                lang,
            )
            AudioService.generate_cluster_audio(cluster_id, audio_content, lang)
    except Exception as audio_err:
        log.error(f"[tasks] Failed to auto-generate cluster audio for {cluster_id} ({lang}): {audio_err}")

    return {
        "synthesis_persisted": True,
        "fast_synthesis_succeeded": bool(fast_mode),
        "shared_computed": updated_shared_computed,
    }


def finalize_cluster_synthesis(
    *,
    cluster_id: str,
    article_rows,
    shared_metrics: dict,
    synthesis_persisted: bool,
    shared_computed: bool,
) -> None:
    """Cluster-wide metadata, events, imagery, and cache refresh after synthesis."""
    if not synthesis_persisted and not shared_computed:
        log.error(f"All synthesis attempts failed for cluster {cluster_id}")
        return

    db.execute(
        """
        UPDATE cluster_metadata
        SET impact_score = %s, impact_explanation = %s
        WHERE cluster_id = %s
    """,
        (shared_metrics["impact_score"], shared_metrics["impact_reasoning"], cluster_id),
        fetch=False,
    )

    try:
        from utils import publish_event

        is_breaking = False
        if article_rows:
            from core.config import BREAKING_SCORE_THRESHOLD
            from utils import score_cluster

            is_breaking = score_cluster(article_rows) >= BREAKING_SCORE_THRESHOLD

        publish_event(
            "updates",
            {
                "type": "cluster_synthesis_updated",
                "cluster_id": cluster_id,
                "is_breaking": is_breaking,
                "impact_score": shared_metrics["impact_score"],
                "headline": article_rows[0].get("title", "") if article_rows else "",
                "time": datetime.datetime.now().isoformat(),
            },
        )
    except Exception as pub_err:
        log.warning(f"[tasks] Failed to publish SSE event for {cluster_id}: {pub_err}")

    try:
        from nlp.categories import detect_topic

        all_titles = " ".join([a.get("title") or "" for a in article_rows])
        if detect_topic(all_titles) == "Sport":
            from notifier import BreakingNewsNotifier

            from core.config import NTFY_TOPIC
            from nlp.generation import _extract_sports_scores

            latest_scores = _extract_sports_scores(article_rows[0].get("title") or "") + _extract_sports_scores(
                article_rows[0].get("description") or ""
            )
            if latest_scores:
                latest_score = latest_scores[0]
                notifier = BreakingNewsNotifier(NTFY_TOPIC)
                notifier.notify_score_change(article_rows[0].get("title"), latest_score, cluster_id)
    except Exception as exc:
        log.warning(f"[tasks/sports] Score alert failed: {exc}")

    strong_img = db.execute_one(
        f"SELECT 1 FROM articles WHERE cluster_id = %s AND {STRONG_IMAGE_SQL_FILTER} LIMIT 1",
        (cluster_id,),
    )
    if not strong_img:
        summary_row = db.execute_one(
            "SELECT summary FROM cluster_summaries WHERE cluster_id = %s LIMIT 1", (cluster_id,)
        )
        if summary_row:
            svg_content = generate_local_placeholder(cluster_id, summary_row["summary"])
            img_url = generate_cover_art(cluster_id, svg_content)
            if img_url:
                db.execute(
                    "UPDATE articles SET image_url = %s WHERE cluster_id = %s AND (image_url IS NULL OR image_url LIKE '%%placeholder%%')",
                    (img_url, cluster_id),
                    fetch=False,
                )

    try:
        invalidate_cluster_caches(cluster_id)
        if os.environ.get("REDIS_URL"):
            from tasks.intelligence.metadata import generate_cluster_metadata_task
            from tasks.utils import schedule_task_once

            schedule_task_once(
                f"lock:cluster_metadata:{cluster_id}",
                int(os.environ.get("CLUSTER_METADATA_LOCK_TTL_SECONDS", "900")),
                generate_cluster_metadata_task,
                kwargs={"target_clusters": [cluster_id]},
                countdown=5,
                queue="maintenance",
            )
    except Exception as err:
        log.warning(f"[tasks] Finalization error for {cluster_id}: {err}")
