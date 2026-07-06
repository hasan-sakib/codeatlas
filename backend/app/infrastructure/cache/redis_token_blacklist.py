from redis.asyncio import Redis

from app.domain.ports.token_blacklist import TokenBlacklistPort

_KEY_PREFIX = "auth:blacklist:"


class RedisTokenBlacklistAdapter(TokenBlacklistPort):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def blacklist(self, jti: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            # Token has already expired naturally — nothing to blacklist.
            return
        await self._redis.setex(f"{_KEY_PREFIX}{jti}", ttl_seconds, "1")

    async def is_blacklisted(self, jti: str) -> bool:
        return bool(await self._redis.exists(f"{_KEY_PREFIX}{jti}"))
