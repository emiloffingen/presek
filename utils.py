import datetime
import logging
import math
import redis
import json
import os
import time
from config import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY

log = logging.getLogger("presek")
redis_client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
_SOURCE_STATUS_CACHE = {"time": 0.0, "data": {}}

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle datetime objects."""
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return super().default(obj)

def cached_response(key: str, ttl: int = 60):
    try:
        val = redis_client.get(key)
        if val:
            # We don't have a generic way to deserialize ISO strings back to datetime
            # without knowing the schema, so we keep them as strings. 
            # Flask's jsonify handles ISO strings well.
            return json.loads(val)
    except Exception as e:
        log.warning(f"[cache] read error on {key}: {e}")
    return None

def set_cache(key: str, val, ttl: int = 60):
    try:
        redis_client.setex(key, ttl, json.dumps(val, cls=DateTimeEncoder))
    except Exception as e:
        log.warning(f"[cache] write error on {key}: {e}")

def delete_cache(key: str):
    try:
        redis_client.delete(key)
    except Exception as e:
        log.warning(f"[cache] delete error on {key}: {e}")

def delete_cache_prefix(prefix: str):
    try:
        cursor = 0
        pattern = f"{prefix}*"
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                redis_client.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        log.warning(f"[cache] prefix delete error on {prefix}: {e}")

RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 60     # requests per window

def check_rate_limit(ip: str) -> bool:
    """Redis-backed rate limiter using a sliding window approach."""
    key = f"rate_limit:{ip}"
    now = time.time()
    
    try:
        # Use Redis pipeline for atomic operations
        pipe = redis_client.pipeline()
        # Remove timestamps older than the window
        pipe.zremrangebyscore(key, 0, now - RATE_LIMIT_WINDOW)
        # Count current requests in the window
        pipe.zcard(key)
        # Add the new request timestamp
        pipe.zadd(key, {str(now): now})
        # Set expiration on the key so it cleans up after inactivity
        pipe.expire(key, RATE_LIMIT_WINDOW)
        
        results = pipe.execute()
        current_count = results[1]
        
        if current_count >= RATE_LIMIT_MAX:
            return False
        return True
    except Exception as e:
        # Fail-open: Redis outage should not take down the site
        log.warning(f"[rate_limit] Redis unavailable for {ip}, allowing request: {e}")
        return True

def calculate_reading_time(text: str) -> int:
    """Estimates reading time in minutes (approx 200 wpm)."""
    if not text: return 1
    words = len(text.split())
    return max(1, math.ceil(words / 200))


def get_source_health_map(ttl_seconds: int = 60):
    now = time.time()
    if _SOURCE_STATUS_CACHE["data"] and now - _SOURCE_STATUS_CACHE["time"] < ttl_seconds:
        return _SOURCE_STATUS_CACHE["data"]
    try:
        raw = redis_client.hgetall("presek:source_statuses") or {}
        parsed = {key: json.loads(value) for key, value in raw.items()}
        _SOURCE_STATUS_CACHE["time"] = now
        _SOURCE_STATUS_CACHE["data"] = parsed
        return parsed
    except Exception as e:
        log.warning(f"[source_health] Redis unavailable, using static credibility only: {e}")
        return _SOURCE_STATUS_CACHE["data"] or {}


def get_source_quality_multiplier(source: str) -> float:
    status = get_source_health_map().get(source) or {}
    quality_score = status.get("quality_score")
    if quality_score is None:
        return 1.0
    try:
        quality_score = float(quality_score)
    except Exception:
        return 1.0
    return max(0.45, min(1.05, 0.55 + quality_score * 0.5))


def get_source_effective_weight(source: str) -> float:
    base = SOURCE_CREDIBILITY.get(source, DEFAULT_CREDIBILITY)
    return base * get_source_quality_multiplier(source)

def score_cluster(arts):
    """
    PageRank-style cluster importance score.
    Combines:
      - Source count (breadth of coverage)
      - Credibility-weighted source score
      - Recency (decays over 24h)
    """
    now = datetime.datetime.now()

    # Credibility score — sum of weights of unique sources
    unique_sources = {a["source"] for a in arts}
    cred_score = sum(
        get_source_effective_weight(s)
        for s in unique_sources
    )

    # Recency score — exponential decay, half-life = 6 hours
    try:
        ts = arts[0]["created_at"]
        if isinstance(ts, datetime.datetime):
            latest = ts.replace(tzinfo=None)
        else:
            latest = datetime.datetime.fromisoformat(ts.replace("+00:00", ""))
        hours_old = (now - latest).total_seconds() / 3600
    except Exception:
        hours_old = 24
    recency = math.exp(-0.115 * hours_old)  # e^(-ln2/6 * h) ≈ halves every 6h

    # Source count bonus (logarithmic — diminishing returns)
    breadth = math.log1p(len(arts))

    # Click engagement bonus
    total_clicks = sum(a.get("clicks", 0) or 0 for a in arts)
    click_bonus = 1 + math.log1p(total_clicks) * 0.15

    return cred_score * recency * breadth * click_bonus


def score_cluster_for_synthesis(arts):
    """
    Prioritization score for deciding which clusters deserve synthesis first.
    Compared to score_cluster(), this puts more weight on:
      - multi-source breadth and source diversity
      - likely disagreement / angle diversity across titles
      - user attention
      - the presence of enough context to produce a worthwhile synthesis
    """
    if not arts:
        return 0.0

    ranked = rank_articles_in_cluster(arts)
    base_score = score_cluster(ranked)
    unique_sources = {a.get("source") for a in ranked if a.get("source")}
    source_count = len(unique_sources)
    source_bonus = 1 + min(0.8, math.log1p(source_count) * 0.28)

    # More description text means the synthesizer has more evidence to work with.
    described_articles = sum(1 for a in ranked if str(a.get("description") or "").strip())
    context_bonus = 1 + min(0.35, described_articles * 0.08)

    # If titles diverge lexically, there is more likely angle diversity worth summarizing.
    title_terms = []
    for article in ranked[:6]:
        terms = {
            token
            for token in str(article.get("title") or "").lower().split()
            if len(token) >= 4
        }
        if terms:
            title_terms.append(terms)

    disagreement_bonus = 1.0
    if len(title_terms) >= 2:
        overlaps = []
        for idx in range(len(title_terms) - 1):
            left = title_terms[idx]
            right = title_terms[idx + 1]
            union = len(left | right) or 1
            overlaps.append(len(left & right) / union)
        if overlaps:
            avg_overlap = sum(overlaps) / len(overlaps)
            disagreement_bonus = 1 + max(0.0, min(0.28, (0.55 - avg_overlap) * 0.7))

    return base_score * source_bonus * context_bonus * disagreement_bonus


def _coerce_datetime(value):
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00").replace("+00:00", ""))
    except Exception:
        return None


def _number_tokens(text: str) -> set[str]:
    import re
    return set(re.findall(r"\b\d+(?::\d+)?(?:[%.,]\d+)?\b", str(text or "")))


def _title_overlap(left: str, right: str) -> float:
    left_terms = {token for token in str(left or "").lower().split() if len(token) >= 4}
    right_terms = {token for token in str(right or "").lower().split() if len(token) >= 4}
    union = len(left_terms | right_terms) or 1
    return len(left_terms & right_terms) / union


def assess_cluster_synthesis_freshness(arts, synthesis_created_at):
    """
    Decide whether an existing synthesis should be refreshed based on
    meaningful cluster changes after the last synthesis time.
    """
    if not arts:
        return {
            "has_synthesis": bool(synthesis_created_at),
            "refresh_needed": False,
            "is_stale": False,
            "freshness_score": 0.0,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": None,
            "synthesis_updated_at": _coerce_datetime(synthesis_created_at),
        }

    ranked = rank_articles_in_cluster(arts)
    synthesis_dt = _coerce_datetime(synthesis_created_at)
    latest_article_at = max((_coerce_datetime(a.get("created_at")) for a in ranked), default=None)

    if not synthesis_dt:
        return {
            "has_synthesis": False,
            "refresh_needed": True,
            "is_stale": False,
            "freshness_score": 10.0,
            "reasons": ["missing_synthesis"],
            "new_article_count": len(ranked),
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": None,
        }

    newer_articles = []
    older_articles = []
    for article in ranked:
        article_dt = _coerce_datetime(article.get("created_at"))
        if article_dt and article_dt > synthesis_dt:
            newer_articles.append(article)
        else:
            older_articles.append(article)

    if not newer_articles:
        return {
            "has_synthesis": True,
            "refresh_needed": False,
            "is_stale": False,
            "freshness_score": 0.0,
            "reasons": [],
            "new_article_count": 0,
            "latest_article_at": latest_article_at,
            "synthesis_updated_at": synthesis_dt,
        }

    score = 0.0
    reasons = []

    newer_sources = {a.get("source") for a in newer_articles if a.get("source")}
    older_sources = {a.get("source") for a in older_articles if a.get("source")}
    net_new_sources = sorted(source for source in newer_sources if source not in older_sources)
    if net_new_sources:
        score += min(1.6, 0.9 + len(net_new_sources) * 0.35)
        reasons.append("new_sources")

    newer_numbers = set()
    older_numbers = set()
    for article in newer_articles:
        newer_numbers |= _number_tokens(" ".join([str(article.get("title") or ""), str(article.get("description") or "")]))
    for article in older_articles:
        older_numbers |= _number_tokens(" ".join([str(article.get("title") or ""), str(article.get("description") or "")]))
    if newer_numbers - older_numbers:
        score += 0.95
        reasons.append("new_numbers")

    if older_articles:
        newest_title = str(newer_articles[0].get("title") or "")
        baseline_title = str(older_articles[0].get("title") or "")
        if newest_title and baseline_title and _title_overlap(newest_title, baseline_title) < 0.26:
            score += 0.85
            reasons.append("new_angle")

    if len(newer_articles) >= 2:
        score += 0.45
        reasons.append("multiple_new_reports")

    high_weight_new_source = any(get_source_effective_weight(str(article.get("source") or "")) >= 1.45 for article in newer_articles)
    if high_weight_new_source:
        score += 0.55
        reasons.append("credible_new_reporting")

    current_score = score_cluster_for_synthesis(ranked)
    if current_score >= 3.5:
        score += 0.35
        reasons.append("high_priority_cluster")

    age_minutes = max(0.0, ((latest_article_at or synthesis_dt) - synthesis_dt).total_seconds() / 60.0)
    cooldown_active = age_minutes < 20 and len(newer_articles) == 1 and not net_new_sources and not (newer_numbers - older_numbers)
    refresh_needed = score >= 1.2 and not cooldown_active

    return {
        "has_synthesis": True,
        "refresh_needed": refresh_needed,
        "is_stale": refresh_needed,
        "freshness_score": round(score, 3),
        "reasons": reasons,
        "new_article_count": len(newer_articles),
        "latest_article_at": latest_article_at,
        "synthesis_updated_at": synthesis_dt,
    }


def rank_articles_in_cluster(arts):
    """Within a cluster, put the most credible source first."""
    return sorted(
        arts,
        key=lambda a: get_source_effective_weight(a["source"]),
        reverse=True
    )

def is_balanced(arts) -> bool:
    """True if cluster contains 3+ unique sources from different categories."""
    from config import SOURCE_CATEGORIES, BALANCED_COVERAGE_THRESHOLD
    if len(arts) < BALANCED_COVERAGE_THRESHOLD:
        return False
    
    unique_categories = {SOURCE_CATEGORIES.get(a["source"], "Локални") for a in arts}
    unique_sources = {a["source"] for a in arts}
    
    # Balanced if 3+ sources OR 2+ distinct categories (e.g. Mainstream + Independent)
    return len(unique_sources) >= 4 or len(unique_categories) >= 2

def publish_event(channel: str, data: dict):
    """Broadcast a JSON message to a Redis channel."""
    try:
        redis_client.publish(channel, json.dumps(data, cls=DateTimeEncoder))
    except Exception as e:
        log.warning(f"[pubsub] publish error on {channel}: {e}")

def event_stream(channel: str):
    """Generator for Server-Sent Events (SSE) subscribing to a Redis channel."""
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)
    # Send an initial "ping" to keep connection alive
    yield "retry: 10000\n\n"
    try:
        for message in pubsub.listen():
            if message['type'] == 'message':
                data = message['data']
                yield f"data: {data}\n\n"
    except Exception as e:
        log.error(f"[pubsub] stream error on {channel}: {e}")
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
