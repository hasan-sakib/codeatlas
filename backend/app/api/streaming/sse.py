import asyncio
from collections.abc import AsyncGenerator

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.streaming.events import ErrorEvent, SSEEventName

logger = structlog.get_logger(__name__)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # nginx: disable response buffering for this stream
    "Connection": "keep-alive",
}


def format_sse_event(name: SSEEventName, payload: BaseModel) -> str:
    return f"event: {name.value}\ndata: {payload.model_dump_json()}\n\n"


async def sse_response(
    request: Request,
    event_source: AsyncGenerator[tuple[SSEEventName, BaseModel], None],
    *,
    idle_timeout_s: float = 30.0,
) -> StreamingResponse:
    async def generate() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("sse.client_disconnected")
                    return

                try:
                    name, payload = await asyncio.wait_for(
                        event_source.__anext__(), timeout=idle_timeout_s
                    )
                except StopAsyncIteration:
                    return
                except TimeoutError:
                    logger.warning("sse.idle_timeout", idle_timeout_s=idle_timeout_s)
                    yield format_sse_event(
                        SSEEventName.ERROR,
                        ErrorEvent(type="idle_timeout", title="Stream idle timeout"),
                    )
                    return

                yield format_sse_event(name, payload)
        finally:
            # Guarantees the upstream generator's cleanup (closing the
            # agent graph's async generator, unsubscribing Redis, etc.)
            # runs on every exit path: normal completion, disconnect,
            # idle timeout, or an exception propagating out of this loop.
            await event_source.aclose()

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
