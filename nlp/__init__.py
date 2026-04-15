from nlp.sentiment import analyze_sentiment_locally
from nlp.keywords import (
    extract_keyphrases_locally,
    extract_cluster_tags_locally,
    filter_cluster_tags,
    normalize_tag_name,
    is_valid_focus_entity
)
from nlp.text_processing import (
    lemmatize_mk,
    rewrite_to_macedonian_locally,
    _jaccard_similarity,
    synthesize_locally
)
from nlp.generation import (
    summarize_article_fallback,
    synthesize_cluster_fallback,
    generate_daily_brief_fallback,
    compare_cluster_sources,
    generate_local_placeholder,
    summarize_locally
)

# Export for easier access
__all__ = [
    'analyze_sentiment_locally',
    'extract_keyphrases_locally',
    'extract_cluster_tags_locally',
    'filter_cluster_tags',
    'normalize_tag_name',
    'is_valid_focus_entity',
    'lemmatize_mk',
    'rewrite_to_macedonian_locally',
    'summarize_article_fallback',
    'synthesize_cluster_fallback',
    'generate_daily_brief_fallback',
    'compare_cluster_sources',
    'generate_local_placeholder',
    'summarize_locally',
    'synthesize_locally'
]
