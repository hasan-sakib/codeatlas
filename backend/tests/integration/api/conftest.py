import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

import app.infrastructure.db.models  # noqa: F401  registers all tables on Base.metadata
from app.core.config import clear_settings_cache
from app.infrastructure.cache.redis_client import clear_redis_client_cache
from app.infrastructure.db.base import Base
from app.infrastructure.db.session import clear_sessionmaker_cache
from app.main import create_app


@pytest_asyncio.fixture
async def api_client(postgres_container, redis_container, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE__URL", postgres_container.get_connection_url())
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    monkeypatch.setenv("REDIS__URL", f"redis://{redis_host}:{redis_port}/0")
    monkeypatch.setenv("QDRANT__URL", "http://localhost:6333")
    monkeypatch.setenv("OLLAMA__BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("SECURITY__JWT_SECRET_KEY", "integration-test-secret-key-value")

    clear_settings_cache()
    clear_sessionmaker_cache()
    clear_redis_client_cache()

    # Fresh throwaway engine just for schema setup — never reused, so it
    # can't leak a stale event-loop-bound asyncpg connection into the
    # app's own (separately cached) engine.
    schema_engine = create_async_engine(postgres_container.get_connection_url())
    async with schema_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await schema_engine.dispose()

    with TestClient(create_app()) as client:
        yield client

    clear_settings_cache()
    clear_sessionmaker_cache()
    clear_redis_client_cache()
