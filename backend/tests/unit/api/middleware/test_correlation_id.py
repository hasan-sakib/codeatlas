import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.correlation_id import CORRELATION_ID_HEADER, CorrelationIdMiddleware
from app.api.middleware.error_handling import register_exception_handlers
from app.core.logging import get_correlation_id


class _ListHandler(logging.Handler):
    """Captures formatted log lines directly via the logging module,
    independent of stdout/stderr — TestClient runs the ASGI app in a
    background thread (anyio blocking portal), which fights with pytest's
    capsys (confirmed empirically: capsys.readouterr() came back empty,
    then raised "I/O operation on closed file" once the background thread
    held a stale stdout reference). Handler-based capture is thread-safe
    because logging dispatch is internally synchronized regardless of
    which thread emits a record.
    """

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def test_correlation_id_generated_when_header_absent(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert CORRELATION_ID_HEADER in response.headers
    assert len(response.headers[CORRELATION_ID_HEADER]) == 36  # UUID4 string form


def test_correlation_id_echoes_incoming_header(client: TestClient) -> None:
    response = client.get("/health", headers={CORRELATION_ID_HEADER: "my-custom-id"})

    assert response.headers[CORRELATION_ID_HEADER] == "my-custom-id"


def test_correlation_id_cleared_after_request(client: TestClient) -> None:
    client.get("/health", headers={CORRELATION_ID_HEADER: "leaked-id"})

    assert get_correlation_id() is None


def test_correlation_id_appears_in_route_handler_logs(client: TestClient) -> None:
    # structlog.testing.capture_logs() deliberately excludes merge_contextvars
    # from its processor chain (confirmed by reading its source), so it can
    # never see contextvar-bound fields like correlation_id. Attach a
    # handler using configure_logging()'s own formatter to observe the
    # real rendered output instead.
    root_logger = logging.getLogger()
    formatter = root_logger.handlers[0].formatter
    test_handler = _ListHandler()
    test_handler.setFormatter(formatter)
    root_logger.addHandler(test_handler)
    try:
        response = client.get("/health")
    finally:
        root_logger.removeHandler(test_handler)

    correlation_id = response.headers[CORRELATION_ID_HEADER]

    assert any(correlation_id in line for line in test_handler.lines)
    assert any("health_check.requested" in line for line in test_handler.lines)


def test_correlation_id_survives_into_an_unhandled_exception_response() -> None:
    # Regression test: CorrelationIdMiddleware used to clear the
    # correlation id in a bare `finally`, which ran *before* Starlette's
    # ServerErrorMiddleware (outside every user-added middleware) got to
    # dispatch to the registered Exception handler — so every 500
    # response's correlation_id came back None. Verified directly against
    # a real FastAPI app + TestClient, not just reasoned about.
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("unexpected")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json()["correlation_id"] == response.headers.get(CORRELATION_ID_HEADER)
    assert response.json()["correlation_id"] is not None
