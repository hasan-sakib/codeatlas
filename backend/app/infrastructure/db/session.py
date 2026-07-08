from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.db.engine import get_engine


def get_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@lru_cache(maxsize=1)
def _get_cached_sessionmaker() -> async_sessionmaker[AsyncSession]:
    from app.core.config import get_settings

    engine = get_engine(get_settings().database)
    return get_sessionmaker(engine)


def clear_sessionmaker_cache() -> None:
    """Test-only helper, mirrors app.core.config.clear_settings_cache.
    Required whenever a test changes DATABASE__URL and needs a fresh
    engine bound to its own event loop (see Module 4's integration-test
    lesson: asyncpg connections can't cross event loops)."""
    _get_cached_sessionmaker.cache_clear()


@asynccontextmanager
async def db_session_context() -> AsyncIterator[AsyncSession]:
    """Commit-on-success/rollback-on-exception/always-close session
    scope, usable as a plain async context manager rather than a FastAPI
    dependency.

    Needed for any DB work that must happen *during* a StreamingResponse
    body's execution (e.g. the LangGraph agent's finalize node persisting
    the assistant's message) — verified directly that FastAPI's
    Depends(get_db_session) commits and closes its session *before* a
    StreamingResponse's body generator starts running, not after. Using
    the request-scoped session for that work silently loses the write:
    it runs against an already-closed session with nothing left to
    commit it. See app/api/routers/conversations.py's send_message.
    """
    sessionmaker = _get_cached_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success,
    rolled back on exception, always closed. Celery tasks use their own
    session-per-task pattern instead (see UnitOfWork), since a
    generator-based dependency doesn't fit Celery's execution model.

    Do not rely on this dependency's cleanup timing for work that must
    happen inside a StreamingResponse body — see db_session_context().
    """
    async with db_session_context() as session:
        yield session
