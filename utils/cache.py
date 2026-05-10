import redis
import os
import json
import logging
import datetime
import time
import asyncio
from typing import Any, Optional
from utils.time import DateTimeEncoder

log = logging.getLogger("presek")

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
    redis_client.ping()
    log.info(f"Redis connected: {redis_url.split('@')[-1].split('/')[0]}")
except redis.ConnectionError as e:
    log.error(f"Redis connection failed to {redis_url}: {e}")
    redis_client = redis.Redis.from_url(
        "redis://localhost:6379/0", decode_responses=True
    )
except Exception as e:
    log.error(f"Redis initialization error: {e}")
    redis_client = redis.Redis.from_url(
        "redis://localhost:6379/0", decode_responses=True
    )

def cached_response(key: str, ttl: int = 60) -> Optional[Any]:
    """Read a cached JSON value from Redis."""
    try:
        val = redis_client.get(key)
        if val:
            return json.loads(val)
    except Exception as e:
        log.warning(f"[cache] redis read error on {key}: {e}")
    return None

def set_cache(key: str, val, ttl: int = 60):
    """Write a JSON value to Redis cache."""
    try:
        json_val = json.dumps(val, cls=DateTimeEncoder)
        redis_client.setex(key, ttl, json_val)
    except Exception as e:
        log.warning(f"[cache] write error on {key}: {e}")

def delete_cache(key: str):
    """Delete a key from Redis cache."""
    try:
        redis_client.delete(key)
    except Exception as e:
        log.warning(f"[cache] delete error on {key}: {e}")

def delete_cache_prefix(prefix: str):
    """Delete all keys with a given prefix from Redis."""
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

def record_runtime_event(event: str, **fields):
    """Record an application event to Redis for analytics."""
    event = str(event or "").strip()
    if not event:
        return

    normalized_fields = {
        str(k): str(v) for k, v in fields.items() if v is not None and str(v) != ""
    }
    field_suffix = "|".join(
        f"{k}={normalized_fields[k]}" for k in sorted(normalized_fields)
    )
    bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    counter_key = f"presek:runtime_events:{bucket}"
    counter_field = event if not field_suffix else f"{event}|{field_suffix}"

    try:
        redis_client.hincrby(counter_key, counter_field, 1)
        redis_client.expire(counter_key, 60 * 60 * 24 * 14)
    except Exception as e:
        log.warning(f"[runtime_event] Redis unavailable: {e}")

    log.info(
        f"[runtime_event] {event} {json.dumps(normalized_fields, ensure_ascii=False)}"
    )

def check_rate_limit(ip: str, path: str = "", is_authenticated: bool = False) -> bool:
    """Sliding window rate limiter."""
    if ip in {"127.0.0.1", "::1"}:
        return True

    is_ai = path.endswith("/research") or path.endswith("/analyst")
    max_reqs = 12 if is_ai else 60
    daily_lim = 100 if is_ai else None

    if is_authenticated:
        max_reqs *= 2
        if daily_lim:
            daily_lim *= 2

    tier = "auth" if is_authenticated else "anon"
    scope = "ai" if is_ai else "general"
    key = f"rate_limit:{tier}:{scope}:{ip}"
    now = time.time()

    try:
        if daily_lim:
            bucket = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
            daily_key = f"rate_limit_daily:{tier}:{scope}:{ip}:{bucket}"
            if redis_client.incr(daily_key) > daily_lim:
                return False
            redis_client.expire(daily_key, 172800)

        pipe = redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, now - 60)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, 60)
        results = pipe.execute()
        return results[1] < max_reqs
    except Exception as e:
        log.debug(f"Rate limit check failed: {e}")
        return True

def publish_event(channel: str, data: dict):
    try:
        redis_client.publish(channel, json.dumps(data, cls=DateTimeEncoder))
    except Exception as e:
        log.debug(f"Failed to publish event to {channel}: {e}")

async def event_stream(channel: str, request=None):
    pubsub = redis_client.pubsub()
    pubsub.subscribe(channel)
    try:
        while True:
            if request and await request.is_disconnected():
                break
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg:
                yield f"data: {msg['data']}\n\n"
            else:
                yield "retry: 10000\n\n"
            await asyncio.sleep(0.1)
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
