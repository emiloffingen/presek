"""Centralized runtime limits for API, security middleware, and worker backpressure."""

import os

from core.config import API_MAX_PAGE, API_MAX_Q_LEN

MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_QUERY_PARAM_LENGTH = API_MAX_Q_LEN
MAX_HEADER_VALUE_LENGTH = 2000

INTEL_QUEUE_SOFT_DEFER_LIMIT = int(os.environ.get("INTEL_QUEUE_SOFT_DEFER_LIMIT", "80"))
INTEL_QUEUE_SECONDARY_DEFER_LIMIT = int(os.environ.get("INTEL_QUEUE_SECONDARY_DEFER_LIMIT", "150"))
INTEL_QUEUE_FULL_DEFER_LIMIT = int(os.environ.get("INTEL_QUEUE_FULL_DEFER_LIMIT", "800"))
BACKFILL_QUEUE_DEPTH_LIMIT = int(os.environ.get("BACKFILL_QUEUE_DEPTH_LIMIT", "100"))

CELERY_QUEUE_WARN_DEPTH = int(os.environ.get("CELERY_QUEUE_WARN_DEPTH", "150"))
CELERY_QUEUE_CRITICAL_DEPTH = int(os.environ.get("CELERY_QUEUE_CRITICAL_DEPTH", "500"))

FAST_TRACK_QUEUE_SOFT_LIMIT = int(os.environ.get("FAST_TRACK_QUEUE_SOFT_LIMIT", "80"))
FAST_TRACK_QUEUE_DEFER_LIMIT = int(os.environ.get("FAST_TRACK_QUEUE_DEFER_LIMIT", "150"))
FAST_TRACK_QUEUE_GROOM_DEPTH = int(os.environ.get("FAST_TRACK_QUEUE_GROOM_DEPTH", "60"))

MAINTENANCE_QUEUE_SOFT_LIMIT = int(os.environ.get("MAINTENANCE_QUEUE_SOFT_LIMIT", "80"))
MAINTENANCE_QUEUE_DEFER_LIMIT = int(os.environ.get("MAINTENANCE_QUEUE_DEFER_LIMIT", "120"))

PIPELINE_TOTAL_DEFER_DEPTH = int(os.environ.get("PIPELINE_TOTAL_DEFER_DEPTH", "1200"))

CRAWL_QUEUE_SOFT_LIMIT = int(os.environ.get("CRAWL_QUEUE_SOFT_LIMIT", "150"))
CRAWL_QUEUE_DEFER_LIMIT = int(os.environ.get("CRAWL_QUEUE_DEFER_LIMIT", "400"))
CRAWL_DISPATCH_CAP = int(os.environ.get("CRAWL_DISPATCH_CAP", "30"))
CRAWL_CATCH_UP_LIMIT = int(os.environ.get("CRAWL_CATCH_UP_LIMIT", "120"))

FACT_GROUNDING_MAX_UNGROUNDED = int(os.environ.get("FACT_GROUNDING_MAX_UNGROUNDED", "2"))
FACT_GROUNDING_MAX_UNGROUNDED_FAST = int(os.environ.get("FACT_GROUNDING_MAX_UNGROUNDED_FAST", "4"))

# Synthesis routing profiles: balanced (default), quality, cost
SYNTHESIS_PROFILE = (os.environ.get("SYNTHESIS_PROFILE") or "balanced").strip().lower()

SYNTHESIS_QUALITY_MIN_LOCAL = float(os.environ.get("SYNTHESIS_QUALITY_MIN_LOCAL", "0.65"))
SYNTHESIS_QUALITY_MIN_NVIDIA = float(os.environ.get("SYNTHESIS_QUALITY_MIN_NVIDIA", "0.70"))

SYNTHESIS_MK_TRANSLATE_FROM_SR = os.environ.get("SYNTHESIS_MK_TRANSLATE_FROM_SR", "true").lower() == "true"


def synthesis_local_only() -> bool:
    """When true, cluster synthesis and related translation use Gemma only (no remote LLMs)."""
    return os.environ.get("SYNTHESIS_LOCAL_ONLY", "false").lower() == "true"


def briefing_remote_provider() -> str | None:
    """Optional remote LLM for daily briefings only (e.g. nvidia). Independent of SYNTHESIS_LOCAL_ONLY."""
    raw = (os.environ.get("BRIEFING_REMOTE_PROVIDER") or "").strip().lower()
    if not raw or raw in {"none", "off", "false", "0", "default"}:
        return None
    if raw == "local":
        return "local"
    return raw


def resolve_briefing_ai_providers(provider_override: str | None = None) -> tuple[str | None, list[str] | None]:
    """Return (provider_override, exclude_providers) for daily briefing AI calls."""
    configured = briefing_remote_provider()
    effective = (provider_override or configured or "").strip().lower()
    if not effective:
        return None, None
    if effective == "local":
        return "local", ["nvidia"]
    if effective == "nvidia":
        # Keep Gemma free for synthesis; template fallback if NVIDIA fails.
        return "nvidia", ["local"]
    return None, None


NVIDIA_DAILY_BRIEF_TIMEOUT_SECONDS = int(os.environ.get("NVIDIA_DAILY_BRIEF_TIMEOUT_SECONDS", "600"))


def local_synthesis_enabled() -> bool:
    """When false, Gemma is reserved for article summaries — not cluster synthesis."""
    if synthesis_local_only():
        return True
    return os.environ.get("LOCAL_SYNTHESIS_PREFER_LOCAL", "true").lower() == "true"


SYNTHESIS_GEMMA_BEFORE_DETERMINISTIC = (
    os.environ.get("SYNTHESIS_GEMMA_BEFORE_DETERMINISTIC", "false").lower() == "true"
)

FAST_SYNTHESIS_STUCK_HOURS = int(os.environ.get("FAST_SYNTHESIS_STUCK_HOURS", "24"))
FAST_SYNTHESIS_PENDING_TTL_SECONDS = int(os.environ.get("FAST_SYNTHESIS_PENDING_TTL_SECONDS", str(48 * 3600)))
FAST_SYNTHESIS_UPGRADE_FORCE_AFTER_DEFERS = (
    os.environ.get("FAST_SYNTHESIS_UPGRADE_FORCE_AFTER_DEFERS", "true").lower() == "true"
)
FAST_SYNTHESIS_UPGRADE_QUEUE = os.environ.get("FAST_SYNTHESIS_UPGRADE_QUEUE", "synthesis")
FAST_SYNTHESIS_UPGRADE_SWEEP_LIMIT = int(os.environ.get("FAST_SYNTHESIS_UPGRADE_SWEEP_LIMIT", "25"))
STUCK_FAST_SYNTHESIS_CRITICAL_COUNT = int(os.environ.get("STUCK_FAST_SYNTHESIS_CRITICAL_COUNT", "25"))
FALLBACK_SYNTHESIS_REFRESH_LIMIT = int(os.environ.get("FALLBACK_SYNTHESIS_REFRESH_LIMIT", "30"))
LOW_SCORE_SYNTHESIS_MIN = float(os.environ.get("LOW_SCORE_SYNTHESIS_MIN", "0.75"))
LOW_SCORE_SYNTHESIS_REFRESH_LIMIT = int(os.environ.get("LOW_SCORE_SYNTHESIS_REFRESH_LIMIT", "20"))
SYNTHESIS_REFRESH_HOURLY_CAP = int(os.environ.get("SYNTHESIS_REFRESH_HOURLY_CAP", "120"))
SYNTHESIS_REFRESH_HOURLY_CAP_BURST = int(
    os.environ.get("SYNTHESIS_REFRESH_HOURLY_CAP_BURST", str(SYNTHESIS_REFRESH_HOURLY_CAP * 2))
)
SYNTHESIS_QUEUE_DEFER_LIMIT = int(os.environ.get("SYNTHESIS_QUEUE_DEFER_LIMIT", "60"))
SYNTHESIS_QUEUE_BURST_INTEL_MAX = int(os.environ.get("SYNTHESIS_QUEUE_BURST_INTEL_MAX", "200"))
ROUTER_BALANCED_LOCAL_MAX_ARTICLES = int(os.environ.get("ROUTER_BALANCED_LOCAL_MAX_ARTICLES", "5"))
SYNTHESIS_PERSIST_GAP_WARN = int(os.environ.get("SYNTHESIS_PERSIST_GAP_WARN", "5"))
SYNTHESIS_PERSIST_GAP_CRITICAL = int(os.environ.get("SYNTHESIS_PERSIST_GAP_CRITICAL", "20"))
LOCAL_LLM_LOCK_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_LLM_LOCK_TIMEOUT_SECONDS", "300"))
LOCAL_LLM_SYNTHESIS_LOCK_TIMEOUT_SECONDS = int(
    os.environ.get("LOCAL_LLM_SYNTHESIS_LOCK_TIMEOUT_SECONDS", "120")
)
LOCAL_SYNTHESIS_MAX_TOKENS = int(os.environ.get("LOCAL_SYNTHESIS_MAX_TOKENS", "1500"))
ROUTER_FALLBACK_PRESSURE_LOCAL = os.environ.get("ROUTER_FALLBACK_PRESSURE_LOCAL", "true").lower() == "true"
LOCAL_SYNTHESIS_SIMPLIFIED_SCHEMA = os.environ.get("LOCAL_SYNTHESIS_SIMPLIFIED_SCHEMA", "true").lower() == "true"
