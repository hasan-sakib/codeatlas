import pytest_asyncio
from redis.asyncio import Redis
from testcontainers.redis import RedisContainer


@pytest_asyncio.fixture
async def redis_client(redis_container: RedisContainer):
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client: Redis = Redis.from_url(f"redis://{host}:{port}/0", decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()
