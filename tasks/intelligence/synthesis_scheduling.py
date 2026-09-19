"""Deferred synthesis upgrades, copy-purity retries, and analyst enrichment."""

from __future__ import annotations

import json
import os
import threading

from nlp.local_analyst import analyst
from tasks.intelligence._constants import (
    _FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS,
    _FAST_SYNTHESIS_UPGRADE_LOCK_TTL_SECONDS,
    _analyst_semaphore,
    db,
)
from tasks.intelligence.synthesis_bundle import _ensure_dict
from tasks.intelligence.synthesis_merge import _compute_centroid_from_values
from tasks.utils import log, schedule_task_once


def _schedule_deep_analyst_work(
    *,
    cluster_id: str,
    article_rows: list[dict],
    lang: str,
    synthetic_headline: str,
    summary: str,
    shared_metrics: dict,
    impact_score: float,
    impact_reasoning: str,
    story_so_far: str,
    sentiment_data: dict,
) -> None:
    """Run heavy local analyst enrichment without blocking synthesis persistence."""

    def _run_analyst_logic():
        try:
            with _analyst_semaphore:
                analyst_text = f"NASLOV: {synthetic_headline}\n{summary}"
                deep_metadata = analyst.extract_deep_metadata(analyst_text, lang=lang)
                titles_sources = [f"{a['source']}: {a['title']}" for a in article_rows[:10]]
                pluralism_data = analyst.assess_pluralism(titles_sources, lang=lang)
                deep_metadata = _ensure_dict(deep_metadata)
                pluralism_data = _ensure_dict(pluralism_data)

                entities = deep_metadata.get("entities", [])
                for entity in entities:
                    with db.connection() as conn:
                        with conn.cursor() as cur:
                            try:
                                cur.execute(
                                    """
                                    INSERT INTO knowledge_entities (name, type, last_seen, total_mentions)
                                    VALUES (%s, 'PERSON', NOW(), 1)
                                    ON CONFLICT (name) DO UPDATE SET last_seen = NOW()
                                    """,
                                    (entity,),
                                )
                                cur.execute(
                                    """
                                    INSERT INTO entity_mentions_daily (entity_name, cluster_id, day)
                                    VALUES (%s, %s, CURRENT_DATE)
                                    ON CONFLICT (entity_name, cluster_id, day) DO NOTHING
                                    """,
                                    (entity, cluster_id),
                                )
                                conn.commit()
                            except Exception as entity_err:
                                log.debug(f"Failed to update entity mentions: {entity_err}")
                                conn.rollback()

                pulse_score = deep_metadata.get("pulse", shared_metrics.get("pulse_score", 50))
                pluralism_score = pluralism_data.get("score", shared_metrics.get("pluralism_score", 50))
                analyst_entities = deep_metadata.get("entities") or []
                centroid = _compute_centroid_from_values(
                    [a.get("embedding") for a in article_rows if a.get("embedding")]
                )
                centroid_str = f"[{','.join(map(str, centroid))}]" if centroid and len(centroid) == 384 else None

                db.execute(
                    """
                    UPDATE cluster_summaries
                    SET pulse_score = %s,
                        pluralism_score = %s,
                        analyst_entities = %s,
                        narrative_diversity = %s,
                        centroid = COALESCE(%s, centroid)
                    WHERE cluster_id = %s AND lang = %s
                    """,
                    (
                        float(pulse_score),
                        float(pluralism_score),
                        json.dumps(analyst_entities),
                        json.dumps(pluralism_data),
                        centroid_str,
                        cluster_id,
                        lang,
                    ),
                    fetch=False,
                )
                db.execute(
                    """
                    UPDATE cluster_metadata
                    SET impact_score = %s, impact_explanation = %s
                    WHERE cluster_id = %s
                    """,
                    (impact_score, impact_reasoning, cluster_id),
                    fetch=False,
                )
        except Exception as err:
            log.error(f"[analyst] Background enrichment failed for {cluster_id}: {err}")

    threading.Thread(target=_run_analyst_logic, name=f"analyst-{cluster_id}", daemon=True).start()


def _schedule_fast_synthesis_upgrade(cluster_id: str, content=None) -> bool:
    """Queue a deferred full-quality synthesis after an initial fast-mode publish."""
    from core.runtime_limits import FAST_SYNTHESIS_UPGRADE_QUEUE
    from tasks.intelligence.synthesis import upgrade_fast_synthesis_task

    if os.environ.get("FAST_SYNTHESIS_UPGRADE_ENABLED", "true").lower() != "true":
        return False

    lock_key = f"lock:fast_synthesis_upgrade:{cluster_id}"
    scheduled = schedule_task_once(
        lock_key,
        _FAST_SYNTHESIS_UPGRADE_LOCK_TTL_SECONDS,
        upgrade_fast_synthesis_task,  # noqa: F821
        args=(cluster_id,),
        kwargs={"content": content, "defer_attempt": 0},
        countdown=_FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS,
        queue=FAST_SYNTHESIS_UPGRADE_QUEUE,
    )
    if scheduled:
        log.info(
            "[tasks/synthesis] Scheduled full upgrade for %s in %ss",
            cluster_id,
            _FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS,
        )
    return scheduled


_COPY_PURITY_RETRY_LOCK_TTL_SECONDS = int(os.environ.get("COPY_PURITY_RETRY_LOCK_TTL", "7200"))
_COPY_PURITY_RETRY_DELAY_SECONDS = int(os.environ.get("COPY_PURITY_RETRY_DELAY_SECONDS", "300"))


def _schedule_copy_purity_retry(
    cluster_id: str,
    content,
    *,
    lang: str,
    fast_mode: bool,
) -> bool:
    """Re-queue synthesis when publish is blocked by copy-purity gates."""
    from tasks.intelligence.synthesis import synthesize_cluster_task

    if os.environ.get("COPY_PURITY_RETRY_ENABLED", "true").lower() != "true":
        return False

    queue = "fast-track" if fast_mode else "synthesis"
    lock_key = f"lock:copy_purity_retry:{cluster_id}:{lang}"
    scheduled = schedule_task_once(
        lock_key,
        _COPY_PURITY_RETRY_LOCK_TTL_SECONDS,
        synthesize_cluster_task,
        args=(cluster_id, content),
        kwargs={"fast_mode": fast_mode},
        countdown=_COPY_PURITY_RETRY_DELAY_SECONDS,
        queue=queue,
    )
    if scheduled:
        log.info(
            "[tasks/synthesis] Scheduled copy-purity retry for %s (%s) in %ss",
            cluster_id,
            lang,
            _COPY_PURITY_RETRY_DELAY_SECONDS,
        )
    return scheduled
