from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.api.deps import require_current_user
from app.domain.entities.user import User
from app.infrastructure.cache.redis_client import get_redis_client

_WINDOW_SECONDS = 60


async def _enforce(redis_client: Redis, key: str, max_requests: int, window_seconds: int) -> None:
    # Fixed-window counter (INCR + EXPIRE-on-first-hit), not a true
    # sliding log — simpler, O(1) per request, and close enough for
    # abuse prevention at these limits; a request right at the window
    # boundary can momentarily allow slightly more than max_requests,
    # an accepted trade-off for not tracking per-request timestamps.
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    if count > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(window_seconds)},
        )


def rate_limit_by_ip(get_max_requests: Callable[[], int]) -> Callable[..., Awaitable[None]]:
    """For unauthenticated endpoints (e.g. /auth/login, /auth/register) —
    there is no user yet to key on. `get_max_requests` reads Settings at
    request time (not at decoration/import time, when required env vars
    may not be loaded yet — every other call site in this codebase calls
    get_settings() lazily inside a function body, never at module scope).
    """

    async def dependency(
        request: Request, redis_client: Annotated[Redis, Depends(get_redis_client)]
    ) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:ip:{request.url.path}:{client_ip}"
        await _enforce(redis_client, key, get_max_requests(), _WINDOW_SECONDS)

    return dependency


def rate_limit_by_user(get_max_requests: Callable[[], int]) -> Callable[..., Awaitable[None]]:
    """For authenticated endpoints — composes with require_current_user
    (FastAPI resolves and caches it once per request regardless of how
    many dependencies ask for it), so this never duplicates JWT
    decoding/blacklist-checking logic."""

    async def dependency(
        request: Request,
        user: Annotated[User, Depends(require_current_user)],
        redis_client: Annotated[Redis, Depends(get_redis_client)],
    ) -> None:
        key = f"ratelimit:user:{request.url.path}:{user.id}"
        await _enforce(redis_client, key, get_max_requests(), _WINDOW_SECONDS)

    return dependency
