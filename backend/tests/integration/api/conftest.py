import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from redis.asyncio import Redis
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
    redis_url = f"redis://{redis_host}:{redis_port}/0"
    monkeypatch.setenv("REDIS__URL", redis_url)
    monkeypatch.setenv("QDRANT__URL", "http://localhost:6333")
    monkeypatch.setenv("OLLAMA__BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("SECURITY__JWT_SECRET_KEY", "integration-test-secret-key-value")
    # Skips the real BGE-M3 warm-up in app.main's lifespan — this fixture
    # is the only place in the suite that uses `with TestClient(...)`,
    # which is what actually triggers ASGI lifespan events.
    monkeypatch.setenv("ENVIRONMENT", "test")

    clear_settings_cache()
    clear_sessionmaker_cache()
    clear_redis_client_cache()

    # redis_container is session-scoped (shared across every integration
    # test), but rate-limit counters (Module 17) and the token blacklist
    # are keyed in ways that can collide across tests within that shared
    # instance — verified directly: every test calling register_and_login
    # shares one rate-limit bucket for /auth/login /auth/register (every
    # TestClient request reports the same source "IP"), so tests running
    # later in the session started failing with 429s caused by earlier,
    # unrelated tests. Flushing per test gives each one a clean slate.
    flush_client: Redis = Redis.from_url(redis_url)
    await flush_client.flushdb()
    await flush_client.aclose()

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


def register_and_login(
    client: TestClient, email: str, password: str = "correct-horse-battery"
) -> str:
    """Registers + logs in a fresh user, returning a bearer access token —
    shared by every integration test that needs an authenticated caller.
    """
    register_resp = client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert register_resp.status_code == 201, register_resp.text
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200, login_resp.text
    access_token: str = login_resp.json()["access_token"]
    return access_token
