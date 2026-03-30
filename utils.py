import datetime
import math
import redis
import json
import os
import time
from config import SOURCE_CREDIBILITY, DEFAULT_CREDIBILITY

redis_client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)

def cached_response(key: str, ttl: int = 60):
    try:
        val = redis_client.get(key)
        if val:
            return json.loads(val)
    except Exception as e:
        # We'll use a local logger if possible, but for simplicity let's print or ignore
        pass
    return None

def set_cache(key: str, val, ttl: int = 60):
    try:
        redis_client.setex(key, ttl, json.dumps(val))
    except Exception as e:
        pass

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
        # If Redis fails, fail open (allow request) to prevent blocking users during cache issues
        return True

def calculate_reading_time(text: str) -> int:
    """Estimates reading time in minutes (approx 200 wpm)."""
    if not text: return 1
    words = len(text.split())
    return max(1, math.ceil(words / 200))

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
        SOURCE_CREDIBILITY.get(s, DEFAULT_CREDIBILITY)
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


def rank_articles_in_cluster(arts):
    """Within a cluster, put the most credible source first."""
    return sorted(
        arts,
        key=lambda a: SOURCE_CREDIBILITY.get(a["source"], DEFAULT_CREDIBILITY),
        reverse=True
    )
