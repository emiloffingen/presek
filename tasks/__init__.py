# Explicit imports from each module (replacing star imports for pyflakes compatibility)
from tasks.delivery import (
    generate_all_daily_briefs_task,
    generate_daily_brief_task,
    send_daily_digest_task,
    send_newsletter_task,
    send_profile_breaking_alerts_task,
    send_profile_briefings_task,
    send_profile_weekly_digests_task,
)
from tasks.ingestion_task import auto_repair_sources_task, crawl_article_task, run_ingestion
from tasks.intelligence import (
    auto_summarize_task,
    backfill_cover_art_single_task,
    backfill_cover_art_task,
    classify_topics_task,
    detect_global_story_task,
    discover_storylines_task,
    extract_entities_task,
    generate_cluster_metadata_task,
    generate_embeddings_task,
    recluster_recent_articles_task,
    repair_split_clusters_task,
    refine_knowledge_graph_sentiment_task,
    standardize_article_style_task,
    summarize_article_task,
    synthesize_cluster_task,
)
from tasks.maintenance import run_prune_db

# Explicitly re-export for clarity and auto-discovery
__all__ = [
    "crawl_article_task",
    "run_ingestion",
    "auto_repair_sources_task",
    "standardize_article_style_task",
    "detect_global_story_task",
    "summarize_article_task",
    "synthesize_cluster_task",
    "auto_summarize_task",
    "extract_entities_task",
    "classify_topics_task",
    "recluster_recent_articles_task",
    "repair_split_clusters_task",
    "refine_knowledge_graph_sentiment_task",
    "generate_cluster_metadata_task",
    "backfill_cover_art_single_task",
    "backfill_cover_art_task",
    "generate_embeddings_task",
    "discover_storylines_task",
    "generate_all_daily_briefs_task",
    "generate_daily_brief_task",
    "send_daily_digest_task",
    "send_profile_briefings_task",
    "send_profile_weekly_digests_task",
    "send_profile_breaking_alerts_task",
    "send_newsletter_task",
    "run_prune_db",
]
