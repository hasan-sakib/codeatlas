import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.api.middleware.rate_limit import rate_limit_by_ip
from app.core.config import clear_settings_cache
from app.infrastructure.cache.redis_client import clear_redis_client_cache

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def rate_limit_client(redis_container, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{host}:{port}/0"
    monkeypatch.setenv("REDIS__URL", redis_url)
    monkeypatch.setenv("DATABASE__URL", "postgresql+asyncpg://test:test@localhost:5432/test")
    monkeypatch.setenv("QDRANT__URL", "http://localhost:6333")
    monkeypatch.setenv("OLLAMA__BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("SECURITY__JWT_SECRET_KEY", "test-secret-key")
    clear_settings_cache()
    clear_redis_client_cache()

    flush_client: Redis = Redis.from_url(redis_url)
    await flush_client.flushdb()
    await flush_client.aclose()

    app = FastAPI()

    @app.get("/limited-a", dependencies=[Depends(rate_limit_by_ip(lambda: 3))])
    async def limited_a() -> dict[str, str]:
        return {"path": "a"}

    @app.get("/limited-b", dependencies=[Depends(rate_limit_by_ip(lambda: 1))])
    async def limited_b() -> dict[str, str]:
        return {"path": "b"}

    with TestClient(app) as client:
        yield client


def test_rate_limit_by_ip_allows_up_to_the_limit_then_blocks(
    rate_limit_client: TestClient,
) -> None:
    for _ in range(3):
        assert rate_limit_client.get("/limited-a").status_code == 200

    fourth = rate_limit_client.get("/limited-a")
    assert fourth.status_code == 429
    assert "Retry-After" in fourth.headers


def test_rate_limit_by_ip_keys_are_isolated_per_path(rate_limit_client: TestClient) -> None:
    assert rate_limit_client.get("/limited-b").status_code == 200
    assert rate_limit_client.get("/limited-b").status_code == 429
    # A different path's counter is unaffected by /limited-b's being exhausted.
    assert rate_limit_client.get("/limited-a").status_code == 200
