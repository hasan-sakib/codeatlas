from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.streaming.events import CitationEvent, DoneEvent, SSEEventName, TokenEvent
from app.api.streaming.sse import sse_response

pytestmark = pytest.mark.integration


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/stream")
    async def stream(request: Request):  # type: ignore[no-untyped-def]
        async def event_source():  # type: ignore[no-untyped-def]
            yield (SSEEventName.TOKEN, TokenEvent(text="Hello"))
            yield (SSEEventName.TOKEN, TokenEvent(text=" world"))
            yield (
                SSEEventName.CITATION,
                CitationEvent(
                    chunk_id=request.app.state.chunk_id,
                    file_path="a.py",
                    start_line=1,
                    end_line=2,
                    score=0.9,
                ),
            )
            yield (SSEEventName.DONE, DoneEvent())

        return await sse_response(request, event_source())

    return app


async def test_sse_endpoint_streams_real_asgi_response_end_to_end() -> None:
    app = _build_test_app()
    app.state.chunk_id = uuid4()

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as client,
        client.stream("GET", "/stream") as response,
    ):
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        lines = [line async for line in response.aiter_lines() if line]

    event_names = [line.removeprefix("event: ") for line in lines if line.startswith("event:")]
    assert event_names == ["token", "token", "citation", "done"]
