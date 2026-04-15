from tasks.ingestion import (
    crawl_article_task,
    run_ingestion,
    auto_repair_sources_task
)
from tasks.intelligence import (
    translate_article_task,
    summarize_article_task,
    synthesize_cluster_task,
    auto_summarize_task,
    extract_entities_task,
    classify_topics_task,
    recategorize_clusters_task,
    generate_cluster_metadata_task,
    backfill_cover_art_single_task,
    backfill_cover_art_task,
    generate_embeddings_task
)
from tasks.delivery import (
    generate_daily_brief_task,
    send_daily_digest_task,
    send_telegram_briefing_task,
    send_profile_briefings_task,
    send_profile_weekly_digests_task,
    send_profile_breaking_alerts_task,
    send_newsletter_task
)
from tasks.maintenance import (
    run_prune_db
)

# Define all tasks here for Celery's autodiscover if needed
__all__ = [
    'crawl_article_task',
    'run_ingestion',
    'auto_repair_sources_task',
    'translate_article_task',
    'summarize_article_task',
    'synthesize_cluster_task',
    'auto_summarize_task',
    'extract_entities_task',
    'classify_topics_task',
    'recategorize_clusters_task',
    'generate_cluster_metadata_task',
    'backfill_cover_art_single_task',
    'backfill_cover_art_task',
    'generate_embeddings_task',
    'generate_daily_brief_task',
    'send_daily_digest_task',
    'send_telegram_briefing_task',
    'send_profile_briefings_task',
    'send_profile_weekly_digests_task',
    'send_profile_breaking_alerts_task',
    'send_newsletter_task',
    'run_prune_db'
]
