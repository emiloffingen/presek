"""Simplified summarization tasks using local Gemma 2B.

This module provides Celery tasks for article summarization and cluster synthesis
using only the local Gemma model.
"""

import json

from celery import shared_task
from core.logging_config import get_logger

log = get_logger("presek.tasks.summarization")


@shared_task(
    name="tasks.summarization.summarize_article_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def summarize_article_task(self, article_id: int):
    """Generate a summary for a single article using local Gemma.

    Args:
        article_id: The article ID to summarize
    """
    from core.database import db_manager
    from nlp.summarizer import summarize_article

    try:
        # Fetch article
        article = db_manager.execute_one(
            "SELECT id, title, description, full_content, summary FROM articles WHERE id = %s",
            (article_id,),
        )

        if not article:
            log.warning(f"Article {article_id} not found")
            return {"status": "skipped", "reason": "not_found"}

        # Skip if already summarized
        if article.get("summary"):
            log.info(f"Article {article_id} already summarized, skipping")
            return {"status": "skipped", "reason": "already_summarized"}

        # Use full_content if available, otherwise description
        content = article.get("full_content") or article.get("description") or ""
        if not content:
            log.warning(f"Article {article_id} has no content to summarize")
            return {"status": "skipped", "reason": "no_content"}

        # Generate summary
        title = article.get("title", "")
        summary = summarize_article(title, content)

        if not summary:
            log.warning(f"Failed to generate summary for article {article_id}")
            return {"status": "failed", "reason": "generation_failed"}

        # Store summary
        db_manager.execute(
            "UPDATE articles SET summary = %s WHERE id = %s",
            (summary, article_id),
            fetch=False,
        )

        log.info(f"Summarized article {article_id}")
        return {"status": "success", "article_id": article_id}

    except Exception as e:
        log.error(f"Failed to summarize article {article_id}: {e}")
        raise self.retry(exc=e)


@shared_task(
    name="tasks.summarization.synthesize_cluster_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def synthesize_cluster_task(self, cluster_id: int):
    """Generate a synthesis for a cluster of related articles using local Gemma.

    Args:
        cluster_id: The cluster ID to synthesize
    """
    from core.database import db_manager
    from nlp.summarizer import synthesize_cluster

    try:
        # Fetch cluster articles
        articles = db_manager.execute(
            """SELECT id, title, description, source 
               FROM articles 
               WHERE cluster_id = %s 
               ORDER BY created_at DESC 
               LIMIT 10""",
            (cluster_id,),
        )

        if not articles or len(articles) < 2:
            log.info(f"Cluster {cluster_id} has too few articles, skipping synthesis")
            return {"status": "skipped", "reason": "insufficient_articles"}

        # Check if synthesis already exists
        existing = db_manager.execute_one(
            "SELECT cluster_id FROM cluster_summaries WHERE cluster_id = %s",
            (cluster_id,),
        )

        if existing:
            log.info(f"Cluster {cluster_id} already has synthesis, skipping")
            return {"status": "skipped", "reason": "already_synthesized"}

        # Generate synthesis
        synthesis = synthesize_cluster(articles)

        if not synthesis or not synthesis.get("summary"):
            log.warning(f"Failed to generate synthesis for cluster {cluster_id}")
            return {"status": "failed", "reason": "generation_failed"}

        # Store synthesis
        db_manager.execute(
            """INSERT INTO cluster_summaries 
               (cluster_id, lang, summary, synthetic_headline, generated_article, key_facts)
               VALUES (%s, 'mk', %s, %s, %s, %s::jsonb)
               ON CONFLICT (cluster_id, lang) DO UPDATE SET
                 summary = EXCLUDED.summary,
                 synthetic_headline = EXCLUDED.synthetic_headline,
                 generated_article = EXCLUDED.generated_article,
                 key_facts = EXCLUDED.key_facts""",
            (
                cluster_id,
                synthesis.get("summary", ""),
                synthesis.get("headline", ""),
                synthesis.get("summary", ""),  # Use summary as generated_article
                json.dumps(synthesis.get("key_facts", [])),
            ),
            fetch=False,
        )

        log.info(f"Synthesized cluster {cluster_id}")
        return {"status": "success", "cluster_id": cluster_id}

    except Exception as e:
        log.error(f"Failed to synthesize cluster {cluster_id}: {e}")
        raise self.retry(exc=e)


def _ai_cluster_synthesis(articles: list[dict]) -> dict | None:
    """Generate a cluster synthesis via the remote provider cascade.

    Returns {headline, summary, key_facts, provider} or None if unavailable.
    """
    from core.ai_engine import sync_call_ai

    articles_text = ""
    for i, article in enumerate(articles[:10], 1):
        title = (article.get("title") or "").strip()
        desc = (article.get("summary") or article.get("description") or "")[:500]
        source = article.get("source") or ""
        articles_text += f"{i}. [{source}] {title}\n   {desc}\n\n"

    prompt = (
        "Ти си новинарски уредник. На основа на следниве вести за истата тема, "
        "напиши редакциски преглед на македонски јазик.\n\n"
        f"Вести:\n{articles_text}\n"
        "Одговори САМО со валиден JSON без markdown:\n"
        '{"headline": "Краток наслов", "summary": "Резиме од 3-4 реченици", '
        '"key_facts": ["факт 1", "факт 2", "факт 3"]}'
    )

    result = sync_call_ai(
        prompt,
        "Ти си уредник кој пишува на македонски јазик. Враќаш само JSON.",
        task_type="synthesis",
        max_tokens=600,
        json_mode=True,
        lang="mk",
    )
    # sync_call_ai may return (text, provider) or text depending on version.
    provider = "ai"
    text = result
    if isinstance(result, tuple):
        text, provider = result[0], result[1]

    from core.ai_engine import clean_json_response

    parsed = clean_json_response(text or "")
    if not isinstance(parsed, dict) or not parsed:
        return None
    headline = (parsed.get("headline") or "").strip()
    summary = (parsed.get("summary") or "").strip()
    key_facts = parsed.get("key_facts") or []
    # Persist provenance/quality so observability (and low-score regeneration)
    # works on the light scheduled path too. The heavy cascade records these in
    # tasks/intelligence/backfill.py; this path previously dropped them.
    model = None
    quality_score = None
    try:
        from tasks.intelligence.synthesis_generation import _resolve_generation_model
        from tasks.intelligence.synthesis_scoring import _compute_lightweight_quality_score

        model = _resolve_generation_model(provider)
        quality_score = _compute_lightweight_quality_score(headline, summary, summary, key_facts, "mk")
    except Exception as e:  # scoring/provenance must never break generation
        log.debug(f"[synthesis] quality/model resolution skipped: {e}")
    return {
        "headline": headline,
        "summary": summary,
        "key_facts": key_facts,
        "provider": provider or "ai",
        "model": model,
        "quality_score": quality_score,
        "fallback_reason": None,
    }

@shared_task(
    name="tasks.summarization.build_extractive_clusters_task",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def build_extractive_clusters_task(self, hours: int = 48, limit: int = 60, cluster_ids: list[str] | None = None):
    """Build deterministic (LLM-free) overviews for clusters missing synthesis.

    Runs when the AI kill-switch is active. Produces the same shape the UI
    expects (synthetic_headline / summary / key_facts) from source article text.
    """
    from core.database import db_manager
    from nlp.extractive import build_extractive_synthesis

    try:
        if cluster_ids:
            clusters = db_manager.execute(
                """
                SELECT a.cluster_id AS cluster_id
                FROM articles a
                WHERE a.cluster_id = ANY(%s)
                GROUP BY a.cluster_id
                """,
                (list(cluster_ids),),
            )
        else:
            clusters = db_manager.execute(
                """
                SELECT a.cluster_id AS cluster_id,
                       COUNT(*) AS n,
                       COUNT(DISTINCT a.source) AS src
                FROM articles a
                WHERE a.cluster_id IS NOT NULL
                  AND COALESCE(a.ingested_at, a.created_at) >= NOW() - make_interval(hours => %s)
                  AND a.cluster_id NOT IN (
                      SELECT cluster_id FROM cluster_summaries
                      WHERE created_at >= NOW() - make_interval(hours => %s)
                  )
                GROUP BY a.cluster_id
                ORDER BY MAX(COALESCE(a.ingested_at, a.created_at)) DESC
                LIMIT %s
                """,
                (hours, hours, limit),
            )

        if not clusters:
            return {"status": "success", "built": 0}

        built = 0
        for row in clusters:
            cid = row["cluster_id"]
            articles = db_manager.execute(
                """
                SELECT title, description, summary, source
                FROM articles
                WHERE cluster_id = %s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (cid,),
            )
            if not articles:
                continue

            # Prefer real LLM synthesis when AI is enabled; fall back to the
            # deterministic extractive overview when providers are unavailable.
            synth = None
            provider = "extractive"
            try:
                from core.ai_engine import AI_ENABLED
                if AI_ENABLED:
                    synth = _ai_cluster_synthesis(articles)
                    if synth and synth.get("summary"):
                        provider = synth.get("provider", "ai")
            except Exception as ai_err:
                log.warning(f"[synthesis] AI path failed for {cid}: {ai_err}")

            if not synth or not synth.get("summary"):
                synth = build_extractive_synthesis(articles)
                provider = "extractive"

            summary = (synth.get("summary") or "").strip()
            if not summary:
                continue

            generation_model = synth.get("model")
            quality_score = synth.get("quality_score")
            fallback_reason = synth.get("fallback_reason")
            if provider == "extractive":
                fallback_reason = fallback_reason or "extractive_fallback"
            if quality_score is None:
                try:
                    from tasks.intelligence.synthesis_scoring import _compute_lightweight_quality_score

                    quality_score = _compute_lightweight_quality_score(
                        synth.get("headline", ""), summary, summary, synth.get("key_facts", []), "mk"
                    )
                except Exception as e:
                    log.debug(f"[synthesis] lightweight scoring skipped: {e}")

            db_manager.execute(
                """
                INSERT INTO cluster_summaries
                    (cluster_id, lang, summary, synthetic_headline, synthetic_standfirst,
                     generated_article, key_facts, generation_provider, generation_model,
                     quality_score, fallback_reason, created_at)
                VALUES (%s, 'mk', %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NOW())
                ON CONFLICT (cluster_id, lang) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    synthetic_headline = EXCLUDED.synthetic_headline,
                    synthetic_standfirst = EXCLUDED.synthetic_standfirst,
                    generated_article = EXCLUDED.generated_article,
                    key_facts = EXCLUDED.key_facts,
                    generation_provider = EXCLUDED.generation_provider,
                    generation_model = EXCLUDED.generation_model,
                    quality_score = EXCLUDED.quality_score,
                    fallback_reason = EXCLUDED.fallback_reason,
                    created_at = NOW()
                """,
                (
                    cid,
                    summary,
                    synth.get("headline", ""),
                    synth.get("headline", ""),
                    summary,
                    json.dumps(synth.get("key_facts", [])),
                    provider,
                    generation_model,
                    quality_score,
                    fallback_reason,
                ),
                fetch=False,
            )
            built += 1

        log.info(f"[synthesis] Built {built} cluster overviews")
        return {"status": "success", "built": built}

    except Exception as e:
        log.error(f"[extractive] Failed to build cluster overviews: {e}")
        raise self.retry(exc=e)


@shared_task(
    name="tasks.summarization.upgrade_extractive_to_ai_task",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def upgrade_extractive_to_ai_task(self, limit: int = 15, max_age_days: int = 7):
    """Regenerate extractive overviews with a real LLM (throttled, AI-gated).

    No-op when AI is disabled. Processes a small batch per run to respect
    free-tier rate limits; the beat schedule drains the backlog over time.
    """
    from core.ai_engine import AI_ENABLED
    from core.database import db_manager

    if not AI_ENABLED:
        return {"status": "skipped", "reason": "ai_disabled"}


    try:
        rows = db_manager.execute(
            """
            SELECT cs.cluster_id
            FROM cluster_summaries cs
            JOIN articles a ON a.cluster_id = cs.cluster_id
            WHERE cs.generation_provider = 'extractive'
              AND cs.created_at >= NOW() - make_interval(days => %s)
            GROUP BY cs.cluster_id
            HAVING COUNT(*) >= 2
            ORDER BY MAX(COALESCE(a.ingested_at, a.created_at)) DESC
            LIMIT %s
            """,
            (max_age_days, limit),
        )
        upgraded = 0
        for row in rows or []:
            cid = row["cluster_id"]
            articles = db_manager.execute(
                """
                SELECT title, description, summary, source
                FROM articles WHERE cluster_id = %s
                ORDER BY created_at DESC LIMIT 10
                """,
                (cid,),
            )
            if not articles:
                continue
            synth = _ai_cluster_synthesis(articles)
            if not synth or not synth.get("summary"):
                continue
            summary = synth["summary"].strip()
            if not summary:
                continue
            db_manager.execute(
                """
                UPDATE cluster_summaries SET
                    summary = %s,
                    synthetic_headline = %s,
                    synthetic_standfirst = %s,
                    generated_article = %s,
                    key_facts = %s::jsonb,
                    generation_provider = %s,
                    generation_model = %s,
                    quality_score = %s,
                    fallback_reason = NULL,
                    created_at = NOW()
                WHERE cluster_id = %s
                """,
                (
                    summary,
                    synth.get("headline", ""),
                    synth.get("headline", ""),
                    summary,
                    json.dumps(synth.get("key_facts", [])),
                    synth.get("provider", "ai"),
                    synth.get("model"),
                    synth.get("quality_score"),
                    cid,
                ),
                fetch=False,
            )
            upgraded += 1
        log.info(f"[synthesis] Upgraded {upgraded} extractive overviews to AI")
        return {"status": "success", "upgraded": upgraded}
    except Exception as e:
        log.error(f"[synthesis] upgrade_extractive_to_ai failed: {e}")
        raise self.retry(exc=e)


@shared_task(name="tasks.summarization.auto_summarize_task")
def auto_summarize_task():
    """Auto-summarize recent articles and clusters that need processing.

    This task runs periodically via Celery beat to ensure new articles
    get summarized and new clusters get synthesized.
    """
    from core.database import db_manager

    try:
        # 1. Summarize recent articles without summaries
        articles_to_summarize = db_manager.execute(
            """SELECT id FROM articles 
               WHERE summary IS NULL 
                 AND created_at >= NOW() - INTERVAL '6 hours'
               ORDER BY created_at DESC 
               LIMIT 20"""
        )

        summarized_count = 0
        for article in articles_to_summarize:
            try:
                summarize_article_task.delay(article["id"])
                summarized_count += 1
            except Exception as e:
                log.warning(f"Failed to queue article {article['id']}: {e}")

        # 2. Synthesize recent clusters without synthesis
        clusters_to_synthesize = db_manager.execute(
            """SELECT DISTINCT cluster_id 
               FROM articles 
               WHERE cluster_id IS NOT NULL 
                 AND cluster_id NOT IN (SELECT cluster_id FROM cluster_summaries)
                 AND created_at >= NOW() - INTERVAL '12 hours'
               ORDER BY cluster_id DESC 
               LIMIT 10"""
        )

        synthesized_count = 0
        for cluster in clusters_to_synthesize:
            try:
                synthesize_cluster_task.delay(cluster["cluster_id"])
                synthesized_count += 1
            except Exception as e:
                log.warning(f"Failed to queue cluster {cluster['cluster_id']}: {e}")

        log.info(f"Auto-summarize: queued {summarized_count} articles, {synthesized_count} clusters")

        return {
            "status": "success",
            "articles_queued": summarized_count,
            "clusters_queued": synthesized_count,
        }

    except Exception as e:
        log.error(f"Auto-summarize task failed: {e}")
        return {"status": "failed", "error": str(e)}
