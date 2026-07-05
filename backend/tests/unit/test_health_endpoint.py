from fastapi.testclient import TestClient

from app import __version__


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_route_is_registered(client: TestClient) -> None:
    paths = {route.path for route in client.app.routes}

    assert "/health" in paths
