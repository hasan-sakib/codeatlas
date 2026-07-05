import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

import app.infrastructure.db.models  # noqa: F401  registers all tables on Base.metadata
from app.infrastructure.db.base import Base


@pytest.fixture(scope="module")
def postgres_container():
    # Module-scoped: container startup is the expensive part, safe to
    # share since it has no asyncio-event-loop affinity itself.
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container


@pytest_asyncio.fixture
async def db_session(postgres_container: PostgresContainer):
    # Function-scoped: pytest-asyncio gives each test function its own
    # event loop by default, and asyncpg connections/pools are bound to
    # the loop they were created on — reusing a module-scoped engine
    # across tests raised "cannot perform operation: another operation
    # is in progress" (confirmed empirically). A fresh engine per test
    # avoids that; Base.metadata.create_all(checkfirst=True) is cheap
    # to re-run since the tables already exist after the first test.
    engine = create_async_engine(postgres_container.get_connection_url())
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sessionmaker() as session:
        yield session
        await session.rollback()

    await engine.dispose()
