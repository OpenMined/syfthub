"""Redis client for message queue and caching operations."""

from typing import Optional

from redis.asyncio import Redis

from syfthub.core.config import get_settings

# Global Redis client instance (singleton)
_redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """Get or create the Redis client instance.

    Returns:
        Redis: The async Redis client.

    Raises:
        ConnectionError: If unable to connect to Redis.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


async def close_redis_client() -> None:
    """Close the Redis client connection.

    Should be called during application shutdown.
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def check_redis_health() -> bool:
    """Check if Redis is available and responding.

    Returns:
        bool: True if Redis is healthy, False otherwise.
    """
    try:
        client = await get_redis_client()
        await client.ping()
        return True
    except Exception:
        return False
