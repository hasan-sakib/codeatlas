import asyncio
import time

import httpx
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.core.di import provide_qdrant_client
from app.infrastructure.cache.redis_client import get_redis_client
from app.infrastructure.db.session import db_session_context

DEFAULT_TIMEOUT_SECONDS = 2.0


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None
    latency_ms: float | None = None


def _elapsed_ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)


async def check_postgres(timeout_s: float = DEFAULT_TIMEOUT_SECONDS) -> DependencyStatus:
    start = time.monotonic()
    try:

        async def _ping() -> None:
            async with db_session_context() as session:
                await session.execute(text("SELECT 1"))

        await asyncio.wait_for(_ping(), timeout=timeout_s)
        return DependencyStatus(name="postgres", healthy=True, latency_ms=_elapsed_ms(start))
    except Exception as exc:
        return DependencyStatus(
            name="postgres", healthy=False, detail=str(exc), latency_ms=_elapsed_ms(start)
        )


async def check_redis(timeout_s: float = DEFAULT_TIMEOUT_SECONDS) -> DependencyStatus:
    start = time.monotonic()
    try:
        await asyncio.wait_for(get_redis_client().ping(), timeout=timeout_s)
        return DependencyStatus(name="redis", healthy=True, latency_ms=_elapsed_ms(start))
    except Exception as exc:
        return DependencyStatus(
            name="redis", healthy=False, detail=str(exc), latency_ms=_elapsed_ms(start)
        )


async def check_qdrant(timeout_s: float = DEFAULT_TIMEOUT_SECONDS) -> DependencyStatus:
    start = time.monotonic()
    try:
        await asyncio.wait_for(provide_qdrant_client().get_collections(), timeout=timeout_s)
        return DependencyStatus(name="qdrant", healthy=True, latency_ms=_elapsed_ms(start))
    except Exception as exc:
        return DependencyStatus(
            name="qdrant", healthy=False, detail=str(exc), latency_ms=_elapsed_ms(start)
        )


async def check_ollama(timeout_s: float = DEFAULT_TIMEOUT_SECONDS) -> DependencyStatus:
    # No LLMPort/OllamaAdapter method is cheap enough for a readiness
    # probe (complete()/stream_complete() both trigger real generation) —
    # this hits Ollama's own lightweight /api/tags endpoint directly,
    # bypassing the adapter entirely.
    start = time.monotonic()
    base_url = str(get_settings().ollama.base_url).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
        return DependencyStatus(name="ollama", healthy=True, latency_ms=_elapsed_ms(start))
    except Exception as exc:
        return DependencyStatus(
            name="ollama", healthy=False, detail=str(exc), latency_ms=_elapsed_ms(start)
        )


async def check_all_dependencies() -> list[DependencyStatus]:
    return list(
        await asyncio.gather(
            check_postgres(),
            check_redis(),
            check_qdrant(),
            check_ollama(),
        )
    )
