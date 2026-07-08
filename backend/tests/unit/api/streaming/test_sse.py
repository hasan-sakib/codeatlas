from app.api.streaming.events import DoneEvent, SSEEventName, TokenEvent
from app.api.streaming.sse import format_sse_event, sse_response


def test_format_sse_event_produces_exact_wire_format() -> None:
    result = format_sse_event(SSEEventName.TOKEN, TokenEvent(text="hi"))
    assert result == 'event: token\ndata: {"text":"hi"}\n\n'


def test_format_sse_event_done_with_no_message_id() -> None:
    result = format_sse_event(SSEEventName.DONE, DoneEvent())
    assert result == 'event: done\ndata: {"message_id":null}\n\n'


class _FakeRequest:
    def __init__(self, disconnected_after: int | None = None) -> None:
        self._disconnected_after = disconnected_after
        self._checks = 0

    async def is_disconnected(self) -> bool:
        self._checks += 1
        if self._disconnected_after is None:
            return False
        return self._checks > self._disconnected_after


def _make_source(events: list[tuple]):
    async def gen():
        for event in events:
            yield event

    source = gen()
    return source


async def test_sse_response_streams_all_events_in_order_then_ends_cleanly() -> None:
    events = [
        (SSEEventName.TOKEN, TokenEvent(text="a")),
        (SSEEventName.TOKEN, TokenEvent(text="b")),
        (SSEEventName.DONE, DoneEvent()),
    ]
    response = await sse_response(_FakeRequest(), _make_source(events))

    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == [format_sse_event(name, payload) for name, payload in events]


async def test_sse_response_stops_immediately_on_disconnect() -> None:
    events = [
        (SSEEventName.TOKEN, TokenEvent(text="a")),
        (SSEEventName.TOKEN, TokenEvent(text="b")),
    ]
    # Disconnected from the very first check — no event should be yielded.
    response = await sse_response(_FakeRequest(disconnected_after=0), _make_source(events))

    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == []


async def test_sse_response_closes_upstream_generator_on_disconnect() -> None:
    closed = {"value": False}

    async def gen():
        try:
            yield (SSEEventName.TOKEN, TokenEvent(text="a"))
            yield (SSEEventName.TOKEN, TokenEvent(text="b"))
        finally:
            closed["value"] = True

    response = await sse_response(_FakeRequest(disconnected_after=1), gen())
    chunks = [chunk async for chunk in response.body_iterator]

    assert len(chunks) == 1  # got the first event, then disconnect stopped it
    assert closed["value"] is True


async def test_sse_response_emits_error_event_on_idle_timeout() -> None:
    async def gen():
        yield (SSEEventName.TOKEN, TokenEvent(text="a"))
        import asyncio

        await asyncio.sleep(10)  # never reached within the short timeout below
        yield (SSEEventName.TOKEN, TokenEvent(text="never"))  # pragma: no cover

    response = await sse_response(_FakeRequest(), gen(), idle_timeout_s=0.05)
    chunks = [chunk async for chunk in response.body_iterator]

    assert len(chunks) == 2
    assert chunks[0] == format_sse_event(SSEEventName.TOKEN, TokenEvent(text="a"))
    assert "idle_timeout" in chunks[1]
    assert "event: error" in chunks[1]


async def test_sse_response_closes_upstream_generator_even_on_normal_completion() -> None:
    closed = {"value": False}

    async def gen():
        try:
            yield (SSEEventName.DONE, DoneEvent())
        finally:
            closed["value"] = True

    response = await sse_response(_FakeRequest(), gen())
    _ = [chunk async for chunk in response.body_iterator]

    assert closed["value"] is True


async def test_sse_response_sets_streaming_headers() -> None:
    response = await sse_response(_FakeRequest(), _make_source([]))
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
