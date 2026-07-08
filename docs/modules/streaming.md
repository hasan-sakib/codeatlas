# Module 16: Streaming

## Purpose

The shared SSE (`text/event-stream`) transport layer, used by two very different producers: Module 13's agent (chat token/citation/progress/done/error events) and a future indexing-progress publisher (Redis pub/sub, published by whichever module eventually runs the Celery indexing tasks). Centralizing wire format, disconnect handling, and idle-timeout behavior here means both call sites get identical streaming semantics rather than two independently-evolving, potentially-divergent implementations.

## Layering

- `app/api/streaming/events.py` — `SSEEventName`, `TokenEvent`, `CitationEvent`, `ProgressEvent`, `DoneEvent`, `ErrorEvent`.
- `app/api/streaming/sse.py` — `format_sse_event()`, `sse_response()`.
- `app/api/streaming/redis_progress_bridge.py` — `subscribe_to_indexing_progress()`.

No DI wiring needed — these are stateless functions consumed directly by whichever router calls them, not injected ports.

## Scope boundary: the agent-to-SSE adapter lives in Module 17, not here

The design is explicit that the small generator function bridging Module 13's compiled graph output into the `AsyncIterator[tuple[SSEEventName, BaseModel]]` shape `sse_response()` expects belongs in `app/api/routers/conversations.py` — Module 17's file, not this module's. This module owns the generic transport (any producer that yields the right shape works); the agent-specific translation (`astream(..., stream_mode=["custom", "values"])` → `TokenEvent`/`CitationEvent`/`DoneEvent`) is application-specific glue that belongs next to the endpoint using it. Kept this boundary exactly as designed rather than reaching into Module 17's territory to write an end-to-end demo now.

## `subscribe_to_indexing_progress` has no real publisher yet — the consumer is real, the wire contract is documented

No module in this codebase currently publishes to a Redis pub/sub channel during indexing — the indexing pipeline isn't wired up as an orchestrated whole yet (Module 6 only registered `NullIndexingTaskDispatcher`). Rather than defer this file entirely, it's built and tested for real: Redis pub/sub itself is real, already-used infrastructure (Module 5's token blacklist, Module 9's embedding cache), and a consumer can be fully verified by publishing test messages directly in a test, independent of whether a real producer exists yet. The wire contract a future publisher must follow is documented directly in the module's docstring:

- Channel: `f"indexing:progress:{job_id}"`
- Progress message: `{"stage": str, "percent": float | null, "message": str | null}`
- Terminal message: `{"event": "done"}`

Verified directly against a real Redis instance (testcontainers) that `redis.asyncio`'s pubsub `.listen()` yields a `{"type": "subscribe", ...}` confirmation message before any real published message, and that `message["data"]` arrives as `bytes` — both handled explicitly (`type != "message"` is filtered out; `json.loads` accepts bytes directly).

## Disconnect and idle-timeout behavior, verified against a real ASGI response

`sse_response()` checks `await request.is_disconnected()` before waiting for each next event, and wraps the wait in `asyncio.wait_for(..., timeout=idle_timeout_s)`; a `finally` block guarantees `event_source.aclose()` runs on every exit path (normal completion, disconnect, idle timeout). This isn't just reasoned about — it was checked directly:

1. A real `FastAPI` app + `TestClient` round-trip confirms the exact byte sequence and `content-type: text/event-stream; charset=utf-8` header for a normal 3-event stream.
2. A real timeout run (`idle_timeout_s=0.2`, event source sleeps 5s) confirms an `error`/`idle_timeout` SSE event is emitted and the stream ends — not a hang.
3. A real ASGI streaming round-trip via `httpx.AsyncClient(transport=ASGITransport(...))` with `.aiter_lines()` confirms the event sequence survives actual ASGI dispatch, not just direct generator iteration.

## Testing notes

- `test_sse.py`: `format_sse_event` produces the exact wire string (byte-for-byte, including the `\n\n` terminator) for both a populated and an all-default-fields event; `sse_response` streams all events in order and ends cleanly; stops immediately (zero events yielded) when already disconnected on the first check; closes the upstream generator (`finally` block observed via a spy) on disconnect mid-stream, on idle timeout, and on ordinary completion; emits the documented `error`/`idle_timeout` event on timeout; sets the three streaming-specific response headers.
- `test_redis_progress_bridge.py` (integration, real Redis via testcontainers): progress messages arrive in publish order followed by `done`; the generator returns at `done` without waiting for a message published after it (a real ordering/early-exit guarantee, not just "eventually consistent"); a channel scoped to one `job_id` never receives another job's messages (per-job channel isolation, mirroring Module 10's tenant-isolation testing philosophy at a much smaller scale).
- `test_sse_endpoint.py` (integration): a throwaway FastAPI route wired to `sse_response()`, hit through `httpx.AsyncClient` + `ASGITransport` — confirms the whole pipeline survives real ASGI request/response dispatch, not just direct Python generator iteration.
- `pytest -q`: 337 passed (12 new). `mypy app`: no issues, 178 source files (one narrowly-scoped `# type: ignore[no-untyped-call]` for `redis.asyncio`'s untyped `PubSub.aclose`). `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No dedicated live-server smoke test beyond `test_sse_endpoint.py` above — this module has no *production* router of its own yet (that's Module 17's `conversations.py`/indexing-job-progress endpoints); the throwaway test app already exercises the real ASGI streaming path this module is responsible for.
