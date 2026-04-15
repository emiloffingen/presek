from tasks.ingestion import *
from tasks.intelligence import *
from tasks.delivery import *
from tasks.maintenance import *

# Explicitly re-export for clarity and auto-discovery
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
    'discover_storylines_task',
    'generate_daily_brief_task',
    'send_daily_digest_task',
    'send_telegram_briefing_task',
    'send_profile_briefings_task',
    'send_profile_weekly_digests_task',
    'send_profile_breaking_alerts_task',
    'send_newsletter_task',
    'run_prune_db'
]
