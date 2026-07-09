from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.api.routers import health as health_router
from app.core.observability.health_checks import DependencyStatus


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_route_is_registered(client: TestClient) -> None:
    paths = {route.path for route in client.app.routes}

    assert "/health" in paths


def test_liveness_returns_ok_without_checking_dependencies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_check = AsyncMock(side_effect=AssertionError("liveness must never call dependency checks"))
    monkeypatch.setattr(health_router, "check_all_dependencies", mock_check)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
    mock_check.assert_not_called()


def test_readiness_returns_200_when_all_dependencies_healthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_check_all() -> list[DependencyStatus]:
        return [
            DependencyStatus(name="postgres", healthy=True),
            DependencyStatus(name="redis", healthy=True),
            DependencyStatus(name="qdrant", healthy=True),
            DependencyStatus(name="ollama", healthy=True),
        ]

    monkeypatch.setattr(health_router, "check_all_dependencies", _fake_check_all)

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert len(body["dependencies"]) == 4


def test_readiness_returns_503_when_one_dependency_unhealthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_check_all() -> list[DependencyStatus]:
        return [
            DependencyStatus(name="postgres", healthy=True),
            DependencyStatus(name="redis", healthy=True),
            DependencyStatus(name="qdrant", healthy=False, detail="Connection refused"),
            DependencyStatus(name="ollama", healthy=True),
        ]

    monkeypatch.setattr(health_router, "check_all_dependencies", _fake_check_all)

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    unhealthy = [d for d in body["dependencies"] if not d["healthy"]]
    assert [d["name"] for d in unhealthy] == ["qdrant"]
