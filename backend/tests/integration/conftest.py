import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    # Session-scoped: the container itself has no asyncio-event-loop
    # affinity (it's a plain sync context manager around a Docker
    # container), so it's safe to share across every integration test
    # file. Only *engines*/*sessionmakers* built on top of it need to be
    # function-scoped — see Module 4's docs for why.
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as container:
        yield container
