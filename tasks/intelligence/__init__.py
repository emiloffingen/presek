"""Celery-safe no-op intelligence tasks for the MK-only deployment.

The expensive local-AI implementation is disabled on Android, but scheduled
jobs must remain registered so Celery does not discard messages as unknown.
"""

from core.celery_app import celery_app


def _task(name):
    def noop_task(*args, **kwargs):
        return None

    noop_task.__name__ = name.rsplit(".", 1)[-1]
    return celery_app.task(name=name)(noop_task)


auto_summarize_task = _task("tasks.intelligence.auto_summarize_task")
backfill_cover_art_single_task = _task("tasks.intelligence.backfill_cover_art_single_task")
backfill_cover_art_task = _task("tasks.intelligence.backfill_cover_art_task")
classify_topics_task = _task("tasks.intelligence.classify_topics_task")
detect_global_story_task = _task("tasks.intelligence.detect_global_story_task")
detect_global_stories_batch_task = _task("tasks.intelligence.detect_global_stories_batch_task")
discover_storylines_task = _task("tasks.intelligence.discover_storylines_task")
extract_entities_task = _task("tasks.intelligence.extract_entities_task")
generate_cluster_metadata_task = _task("tasks.intelligence.generate_cluster_metadata_task")
generate_embeddings_task = _task("tasks.intelligence.generate_embeddings_task")
recluster_recent_articles_task = _task("tasks.intelligence.recluster_recent_articles_task")
refine_knowledge_graph_sentiment_task = _task("tasks.intelligence.refine_knowledge_graph_sentiment_task")
repair_split_clusters_task = _task("tasks.intelligence.repair_split_clusters_task")
summarize_article_task = _task("tasks.intelligence.summarize_article_task")
summarize_articles_batch_task = _task("tasks.intelligence.summarize_articles_batch_task")
summarize_articles_local_batch_task = _task("tasks.intelligence.summarize_articles_local_batch_task")
synthesize_cluster_task = _task("tasks.intelligence.synthesize_cluster_task")
synthesize_urgent_task = _task("tasks.intelligence.synthesize_urgent_task")
upgrade_fast_synthesis_task = _task("tasks.intelligence.upgrade_fast_synthesis_task")
recategorize_clusters_task = _task("tasks.intelligence.recategorize_clusters_task")
schedule_backfill_cluster_summaries_task = _task("tasks.intelligence.schedule_backfill_cluster_summaries_task")
schedule_backfill_historical_summaries_task = _task("tasks.intelligence.schedule_backfill_historical_summaries_task")


def _dispatch_batched(*args, **kwargs):
    return None


def intelligence_batches_deferred(*args, **kwargs):
    return False


def intelligence_soft_deferred(*args, **kwargs):
    return False
