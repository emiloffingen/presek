"""
Redis Cache Utility for Presek
"""

import json
from typing import Callable, Optional

import redis
from fastapi import Request


class RedisCache:
    """Redis cache client with helper methods"""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
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

    def cache_request(self, expires: int = 3600):
        """Decorator to cache API responses"""

        def decorator(func: Callable):
            async def wrapper(request: Request, *args, **kwargs):
                # Create cache key from request path and query params
                cache_key = f"api:{request.url.path}:{hash(frozenset(request.query_params.items()))}"

                # Try to get from cache
                cached_result = self.get(cache_key)
                if cached_result:
                    return json.loads(cached_result)

                # Execute function and cache result
                result = await func(request, *args, **kwargs)
                self.set(cache_key, json.dumps(result), expires)
                return result

            return wrapper

        return decorator


# Global cache instance
cache = RedisCache()


def get_cache() -> RedisCache:
    """Get the global cache instance"""
    return cache
