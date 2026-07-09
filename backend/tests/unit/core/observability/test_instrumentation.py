from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.observability.instrumentation import setup_prometheus_instrumentator


def test_setup_prometheus_instrumentator_exposes_metrics_endpoint() -> None:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    setup_prometheus_instrumentator(app)

    with TestClient(app) as client:
        client.get("/ping")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_request_duration_seconds" in response.text


def test_metrics_endpoint_is_excluded_from_the_openapi_schema() -> None:
    app = FastAPI()
    setup_prometheus_instrumentator(app)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    assert "/metrics" not in schema["paths"]
