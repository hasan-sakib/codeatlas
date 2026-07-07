import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.qdrant import QdrantContainer

import app.infrastructure.db.models  # noqa: F401  registers all tables on Base.metadata
from app.infrastructure.db.base import Base


@pytest.fixture(scope="module")
def postgres_container():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="module")
def qdrant_container():
    # Pinned to match the installed qdrant-client version — see Module 10.
    with QdrantContainer(image="qdrant/qdrant:v1.18.2") as container:
        yield container


@pytest_asyncio.fixture
async def db_session(postgres_container: PostgresContainer):
    # Function-scoped engine — see Module 4's docs for why (asyncpg
    # connections are bound to the event loop they were created on, and
    # pytest-asyncio gives each test function its own loop).
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
        await session.rollback()

    await engine.dispose()
