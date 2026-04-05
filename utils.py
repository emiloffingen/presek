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
