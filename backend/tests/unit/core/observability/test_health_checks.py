import asyncio

import httpx
import pytest

from app.core.observability import health_checks as hc


def _mock_client_factory(handler: object) -> type:
    class _MockedAsyncClient(httpx.AsyncClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]

    return _MockedAsyncClient


class _FakeSession:
    def __init__(self, *, raise_error: bool = False) -> None:
        self._raise_error = raise_error

    async def execute(self, *args: object, **kwargs: object) -> None:
        if self._raise_error:
            raise ConnectionError("db unreachable")


class _FakeSessionContext:
    def __init__(self, *, raise_error: bool = False, delay_s: float = 0.0) -> None:
        self._session = _FakeSession(raise_error=raise_error)
        self._delay_s = delay_s

    async def __aenter__(self) -> _FakeSession:
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        return self._session

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class _FakeRedis:
    def __init__(self, *, raise_error: bool = False) -> None:
        self._raise_error = raise_error

    async def ping(self) -> bool:
        if self._raise_error:
            raise ConnectionError("redis unreachable")
        return True


class _FakeQdrantClient:
    def __init__(self, *, raise_error: bool = False) -> None:
        self._raise_error = raise_error

    async def get_collections(self) -> object:
        if self._raise_error:
            raise ConnectionError("qdrant unreachable")
        return object()


async def test_check_postgres_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "db_session_context", lambda: _FakeSessionContext())

    result = await hc.check_postgres()

    assert result.name == "postgres"
    assert result.healthy is True
    assert result.detail is None
    assert result.latency_ms is not None and result.latency_ms >= 0


async def test_check_postgres_unhealthy_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "db_session_context", lambda: _FakeSessionContext(raise_error=True))

    result = await hc.check_postgres()

    assert result.healthy is False
    assert "db unreachable" in (result.detail or "")


async def test_check_postgres_unhealthy_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "db_session_context", lambda: _FakeSessionContext(delay_s=1.0))

    result = await hc.check_postgres(timeout_s=0.05)

    assert result.healthy is False


async def test_check_redis_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "get_redis_client", lambda: _FakeRedis())

    result = await hc.check_redis()

    assert result.name == "redis"
    assert result.healthy is True


async def test_check_redis_unhealthy_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "get_redis_client", lambda: _FakeRedis(raise_error=True))

    result = await hc.check_redis()

    assert result.healthy is False
    assert "redis unreachable" in (result.detail or "")


async def test_check_qdrant_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "provide_qdrant_client", lambda: _FakeQdrantClient())

    result = await hc.check_qdrant()

    assert result.name == "qdrant"
    assert result.healthy is True


async def test_check_qdrant_unhealthy_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hc, "provide_qdrant_client", lambda: _FakeQdrantClient(raise_error=True))

    result = await hc.check_qdrant()

    assert result.healthy is False
    assert "qdrant unreachable" in (result.detail or "")


async def test_check_ollama_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": []})

    monkeypatch.setattr(hc.httpx, "AsyncClient", _mock_client_factory(handler))

    result = await hc.check_ollama()

    assert result.name == "ollama"
    assert result.healthy is True


async def test_check_ollama_unhealthy_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    monkeypatch.setattr(hc.httpx, "AsyncClient", _mock_client_factory(handler))

    result = await hc.check_ollama()

    assert result.healthy is False


async def test_check_ollama_unhealthy_on_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(hc.httpx, "AsyncClient", _mock_client_factory(handler))

    result = await hc.check_ollama()

    assert result.healthy is False
    assert result.detail is not None


async def test_check_all_dependencies_runs_all_four_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _fake_check(name: str) -> hc.DependencyStatus:
        calls.append(name)
        return hc.DependencyStatus(name=name, healthy=True)

    monkeypatch.setattr(hc, "check_postgres", lambda: _fake_check("postgres"))
    monkeypatch.setattr(hc, "check_redis", lambda: _fake_check("redis"))
    monkeypatch.setattr(hc, "check_qdrant", lambda: _fake_check("qdrant"))
    monkeypatch.setattr(hc, "check_ollama", lambda: _fake_check("ollama"))

    results = await hc.check_all_dependencies()

    assert {r.name for r in results} == {"postgres", "redis", "qdrant", "ollama"}
    assert all(r.healthy for r in results)
    assert set(calls) == {"postgres", "redis", "qdrant", "ollama"}
