from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import DatabaseSettings


def get_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        str(settings.url),
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_pre_ping=True,
        echo=settings.echo,
    )
