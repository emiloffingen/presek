# Re-exporting functions for backward compatibility
from .time import DateTimeEncoder, _coerce_datetime
from .text import format_sources, calculate_reading_time
from .network import _resolve_public_ips, _peer_ip, get_dominant_color
from .cache import (
    redis_client,
    cached_response,
    set_cache,
    delete_cache,
    delete_cache_prefix,
    record_runtime_event,
    check_rate_limit,
    publish_event,
    event_stream,
)
from .db_helpers import get_source_registry
from .ranking import (
    get_source_health_map,
    get_source_quality_multiplier,
    get_source_effective_weight,
    get_source_trust_label,
    _cluster_title_overlap,
    build_cluster_source_signals,
    annotate_cluster_articles,
    rank_articles_in_cluster,
    build_read_next_clusters,
    build_source_reputation_rows,
    build_editor_analytics_payload,
    score_cluster,
    score_cluster_for_synthesis,
    score_cluster_for_homepage,
    assess_cluster_synthesis_freshness,
    is_balanced,
)
