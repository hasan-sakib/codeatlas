from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import bind_correlation_id, clear_correlation_id

CORRELATION_ID_HEADER = "X-Request-ID"
_CORRELATION_ID_HEADER_BYTES = b"x-request-id"


class CorrelationIdMiddleware:
    """Pure ASGI middleware (not BaseHTTPMiddleware).

    BaseHTTPMiddleware runs the downstream app in a separate anyio task
    (via TaskGroup.start_soon, to support streaming responses), which
    breaks contextvars propagation between this middleware and route
    handlers — confirmed empirically: correlation_id bound here never
    appeared in route-handler log entries under BaseHTTPMiddleware.
    A plain ASGI middleware awaits the downstream app in the same
    coroutine/task, so contextvars set here are visible everywhere below.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming = headers.get(_CORRELATION_ID_HEADER_BYTES)
        correlation_id = bind_correlation_id(incoming.decode() if incoming else None)

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = message.setdefault("headers", [])
                response_headers.append((_CORRELATION_ID_HEADER_BYTES, correlation_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        finally:
            clear_correlation_id()
