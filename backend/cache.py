"""
backend/cache.py
Redis caching helper with graceful fallback (no-op if Redis is down).
"""

import json
import hashlib
from typing import Any, Optional
from loguru import logger

try:
    import redis.asyncio as aioredis
    _redis_available = True
except ImportError:
    _redis_available = False

from backend.config import get_settings

settings = get_settings()
_redis_client: Optional[Any] = None


async def get_redis():
    global _redis_client
    if not _redis_available:
        return None
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable, running without cache: {e}")
            _redis_client = None
    return _redis_client


async def cache_get(key: str) -> Optional[Any]:
    r = await get_redis()
    if r is None:
        return None
    try:
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception as e:
        logger.debug(f"Cache GET error: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = None) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        ttl = ttl or settings.cache_ttl_seconds
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        logger.debug(f"Cache SET error: {e}")


async def cache_delete(key: str) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.delete(key)
    except Exception as e:
        logger.debug(f"Cache DEL error: {e}")


def make_cache_key(*parts: str) -> str:
    """Build a cache key from parts."""
    return ":".join(str(p) for p in parts)


def hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]
