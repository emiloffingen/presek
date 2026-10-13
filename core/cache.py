"""
Redis Cache Utility for Presek
"""

import json
from collections.abc import Callable

import redis


class RedisCache:
    """Redis cache client with helper methods"""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def get(self, key: str) -> str | None:
        """Get value from cache"""
        return self.redis.get(key)

    def set(self, key: str, value: str, expires: int = 3600) -> bool:
        """Set value in cache with expiration"""
        return self.redis.set(key, value, ex=expires)

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        return self.redis.delete(key) == 1

    def cache(self, expires: int = 3600):
        """Decorator to cache function results"""

        def decorator(func: Callable):
            def wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                cache_key = f"{func.__name__}:{hash(frozenset(kwargs.items()))}"

                # Try to get from cache
                cached_result = self.get(cache_key)
                if cached_result:
                    return json.loads(cached_result)

                # Execute function and cache result
                result = func(*args, **kwargs)
                self.set(cache_key, json.dumps(result), expires)
                return result

            return wrapper

        return decorator


# Global cache instance
cache = RedisCache()
