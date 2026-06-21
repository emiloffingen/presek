SUPPORTED_LANGS = ["sr", "mk"]
COUNTRY_LANG = {"RS": "sr", "MK": "mk"}

STRONG_IMAGE_SQL_FILTER = """
    image_url IS NOT NULL
    AND image_url NOT LIKE '%%placeholder%%'
    AND image_url NOT LIKE '%%default%%'
    AND image_url NOT LIKE '%%.svg'
    AND image_url NOT LIKE '%%logo%%'
    AND image_url NOT LIKE '%%emblem%%'
    AND image_url NOT LIKE '%%avatar%%'
    AND image_url NOT LIKE '%%icon%%'
    AND image_url NOT LIKE '%%favicon%%'
    AND image_url NOT LIKE '%%sprite%%'
    AND image_url NOT LIKE '%%banner%%'
    AND image_url NOT LIKE '%%social%%'
    AND image_url NOT LIKE '%%fallback%%'
    AND image_url NOT LIKE '%%no-image%%'
"""
import datetime
import json
import os
import re
import sys
import threading

from core.ai_engine import clean_json_response, generate_cover_art
from core.ai_engine import sync_call_ai as _call_ai
from core.celery_app import celery_app
from core.config import CLUSTER_LOOKBACK
from core.database import db_manager as db
from core.embeddings import average_embeddings, parse_embedding_value
from core.limits import (
    BACKFILL_QUEUE_DEPTH_LIMIT as _BACKFILL_QUEUE_DEPTH_LIMIT,
    INTEL_QUEUE_FULL_DEFER_LIMIT as _INTEL_QUEUE_FULL_DEFER_LIMIT,
    INTEL_QUEUE_SECONDARY_DEFER_LIMIT as _INTEL_QUEUE_SECONDARY_DEFER_LIMIT,
    INTEL_QUEUE_SOFT_DEFER_LIMIT as _INTEL_QUEUE_SOFT_DEFER_LIMIT,
)

_analyst_semaphore = threading.Semaphore(int(os.environ.get("INTEL_ANALYST_CONCURRENCY", "4")))
_INTEL_QUEUE_DEFER_LIMIT = _INTEL_QUEUE_FULL_DEFER_LIMIT
_BACKFILL_BATCH_SIZE = int(os.environ.get("BACKFILL_CLUSTERS_PER_RUN", "8"))
_METADATA_BATCH_SIZE = int(os.environ.get("CLUSTER_METADATA_BATCH_SIZE", "25"))
_ARTICLE_BATCH_SIZE = int(os.environ.get("ARTICLE_BATCH_SIZE", "10"))
_REMOTE_SUMMARY_PROVIDERS = ["nvidia"]
_HISTORICAL_SUMMARY_CURSOR_KEY = "backfill:article_summaries:cursor"
_HISTORICAL_SUMMARY_LOCK_KEY = "lock:backfill:historical_summaries"
_HISTORICAL_SUMMARY_DISPATCH_LIMIT = int(os.environ.get("HISTORICAL_SUMMARY_DISPATCH_LIMIT", "80"))
_HISTORICAL_SUMMARY_DISPATCH_MAX = int(os.environ.get("HISTORICAL_SUMMARY_DISPATCH_MAX", "240"))
_HISTORICAL_SUMMARY_QUEUE_BUFFER = int(os.environ.get("HISTORICAL_SUMMARY_QUEUE_BUFFER", "20"))
_FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS = int(os.environ.get("FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS", "1200"))
_FAST_SYNTHESIS_UPGRADE_LOCK_TTL_SECONDS = int(os.environ.get("FAST_SYNTHESIS_UPGRADE_LOCK_TTL_SECONDS", "7200"))
_FAST_SYNTHESIS_UPGRADE_MAX_DEFERS = int(os.environ.get("FAST_SYNTHESIS_UPGRADE_MAX_DEFERS", "6"))


__all__ = [
    "SUPPORTED_LANGS", "COUNTRY_LANG", "STRONG_IMAGE_SQL_FILTER",
    "_analyst_semaphore", "_INTEL_QUEUE_DEFER_LIMIT", "_BACKFILL_BATCH_SIZE",
    "_METADATA_BATCH_SIZE", "_ARTICLE_BATCH_SIZE", "_REMOTE_SUMMARY_PROVIDERS",
    "_HISTORICAL_SUMMARY_CURSOR_KEY", "_HISTORICAL_SUMMARY_LOCK_KEY",
    "_HISTORICAL_SUMMARY_DISPATCH_LIMIT", "_HISTORICAL_SUMMARY_DISPATCH_MAX",
    "_HISTORICAL_SUMMARY_QUEUE_BUFFER", "_FAST_SYNTHESIS_UPGRADE_DELAY_SECONDS",
    "_FAST_SYNTHESIS_UPGRADE_LOCK_TTL_SECONDS", "_FAST_SYNTHESIS_UPGRADE_MAX_DEFERS",
    "clean_json_response", "generate_cover_art", "_call_ai", "celery_app",
    "CLUSTER_LOOKBACK", "db", "average_embeddings", "parse_embedding_value",
    "_BACKFILL_QUEUE_DEPTH_LIMIT", "_INTEL_QUEUE_FULL_DEFER_LIMIT",
    "_INTEL_QUEUE_SECONDARY_DEFER_LIMIT", "_INTEL_QUEUE_SOFT_DEFER_LIMIT",
]
