from collections.abc import AsyncIterator
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


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success,
    rolled back on exception, always closed. Celery tasks use their own
    session-per-task pattern instead (see UnitOfWork), since a
    generator-based dependency doesn't fit Celery's execution model.
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
