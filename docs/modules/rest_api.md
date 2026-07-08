# Module 17: REST API

## Purpose

The complete `/api/v1` HTTP surface: the routers that were still missing (`search`, `docs`, `conversations`), the centralized error-handling/response envelope contract every router now follows, and Redis-backed rate limiting on the endpoints the design calls out (auth, chat, indexing-trigger). This module also closed several gaps left deliberately open by earlier modules — `ManageConversationUseCase`'s CRUD methods (Module 15 built only `create`/`append_message`/`get_context_window`), a real `GenerateDocumentationUseCase` (previously unbuilt), and `RetrievalQuery.repository_id` (the vector store already supported repository-scoped search; nothing wired it through).

## Layering

- `app/api/schemas/common.py` — `Envelope[T]` (list/paginated responses), `ProblemDetail` (RFC 7807 errors).
- `app/api/middleware/error_handling.py` — maps domain exceptions to HTTP status via an exact-type lookup table; registers handlers for `DomainError` and bare `Exception`.
- `app/api/middleware/rate_limit.py` — `rate_limit_by_ip`/`rate_limit_by_user` dependency factories, Redis `INCR`+`EXPIRE` fixed-window counters.
- `app/api/routers/search.py`, `docs.py`, `conversations.py` — the three routers this module actually builds.
- `app/application/use_cases/docs/generate_documentation.py` — new use case, reuses `RetrievalService` + `LLMPort`.
- `app/domain/value_objects/retrieval_query.py` / `app/application/services/retrieval_service.py` — `repository_id` scoping closed here.

## Response envelope and error contract

Single resources return their schema directly; list/paginated responses wrap in `Envelope[T]` (`{"data": [...], "meta": {}}`) per DESIGN.md §16. Errors always come back as `ProblemDetail` (`type`, `title`, `status`, `detail`, `correlation_id`) with matching `application/problem+json`-shaped bodies, produced by one central lookup table (`_STATUS_BY_EXCEPTION_TYPE`) rather than scattered `try/except HTTPException` blocks in each router. Routers that previously translated a domain exception to an `HTTPException` inline (auth/workspaces/repositories) had that logic removed — the exception now simply propagates and the global handler does the translation. The one exception left in place: `RepositoryUrlValidationError` on `repositories.py`, which is **not** a `DomainError` (it's a plain `Exception` from Module 6's URL validator) and would otherwise fall through to the generic 500 handler instead of a 400.

## Two real bugs found in the existing correlation-id middleware

Writing the global exception handler required actually triggering a 500 end-to-end, which surfaced two pre-existing bugs in `CorrelationIdMiddleware` (Module 3) that no prior module's tests exercised:

1. **Correlation ID lost on every unhandled exception.** The middleware's `try/finally: clear_correlation_id()` cleared the ID before Starlette's `ServerErrorMiddleware` (which wraps all user middleware) got a chance to dispatch to the exception handler — so every 500 response had `correlation_id: null`. Fixed by only clearing on the success path (`try/except Exception: raise / else: clear_correlation_id()`), leaving the ID bound for the exception handler to read. Confirmed safe to leave dangling on the error path: `contextvars` are Task-scoped in asyncio, and each HTTP request runs in its own Task, so there's no cross-request leak.
2. **Duplicate `X-Request-ID` header.** Once the handler started setting `X-Request-ID` explicitly on its `ProblemDetail` response, the middleware's response-header injection blindly appended a second one. Fixed by making `send_with_correlation_id` filter-then-replace instead of append.

Both were caught by `tests/unit/api/middleware/test_correlation_id.py`'s new `test_correlation_id_survives_into_an_unhandled_exception_response` test and `test_error_handling.py`'s duplicate-header assertion — not by design review.

## A critical FastAPI bug found building the chat SSE bridge

`send_message` in `conversations.py` bridges the LangGraph agent (Module 13) into an SSE response (Module 16). The first working version persisted the user's message inside the route body (using the request-scoped `Depends(get_db_session)` session) and expected the assistant's reply to persist the same way inside the `StreamingResponse`'s body generator. It didn't — `test_send_message_streams_sse_response_and_persists_both_turns` kept showing only the user turn, even though the SSE stream completed with a `done` event.

Root cause, confirmed with a minimal reproduction script: **a `yield`-based FastAPI dependency's cleanup code runs before a `StreamingResponse`'s body generator starts executing**, not after the response finishes. The request-scoped DB session is closed the moment the router function returns the `StreamingResponse` object — well before ASGI actually calls the generator to produce bytes. Any DB work needed during real stream execution needs its own, independently-scoped session.

Fixed with `db_session_context()` (`app/infrastructure/db/session.py`), an `@asynccontextmanager` wrapping the same commit/rollback/close logic as `get_db_session()`, opened fresh inside the SSE generator itself:

```python
async def event_source() -> AsyncGenerator[tuple[SSEEventName, BaseModel], None]:
    async with db_session_context() as stream_session:
        agent_graph = provide_agent_graph(stream_session)
        async for event in _agent_event_source(agent_graph, initial_state):
            yield event
```

`get_db_session()` now just delegates to `db_session_context()`, so the two never drift.

## Rate limiting

`rate_limit_by_ip(limit_fn)` / `rate_limit_by_user(limit_fn)` are FastAPI dependency factories taking a `Callable[[], int]`, not a raw `int` — deferring `get_settings()` to request time. An earlier version took literal ints evaluated at route-decoration (import) time, which would read `Settings` before required env vars are guaranteed loaded; every other call site in this codebase resolves settings lazily inside function bodies, so this was changed to match. Enforcement is a fixed-window Redis counter (`INCR` then `EXPIRE` only on the first hit in the window), raising `HTTPException(429, headers={"Retry-After": ...})` on breach. Wired onto `/auth/login` (5/min/IP), `/conversations/{id}/messages` (30/min/user), and `POST /repositories` (3/min/user) per DESIGN.md §23.

**Test isolation gotcha**: the integration suite's `redis_container` fixture is session-scoped (shared across every integration test for speed), and every `TestClient` request reports the same source "IP." Once rate limiting was wired in, 9 unrelated tests elsewhere in the suite started failing with spurious 429s from earlier tests' accumulated counters. Fixed by flushing Redis at the start of the `api_client` fixture — each test gets a clean counter state.

## `docs.py` scope decision

Module 17's design only specified the `docs.py` *router*; no prior module built a documentation-generation use case. Rather than fabricate scope or defer the whole endpoint, the user was asked and chose a minimal real implementation: `GenerateDocumentationUseCase` builds a per-scope generic query (file/symbol/module/repository), scopes a `RetrievalQuery` by `repository_id` (+ `path_prefix` for non-repository scopes), and renders the result through `LLMPort.complete()` with a new `docs_generation.jinja` template — reusing `RetrievalService` and `LLMPort` exactly as they already exist, adding no new capability underneath.

## `repository_id` gap closed in `RetrievalQuery`

`VectorStorePort.search_dense`/`search_sparse` (Module 10) already accepted `repository_id` for scoping, but `RetrievalQuery` (Module 11) never exposed it, so nothing above the vector store could actually use it. Both `search.py` and the new `GenerateDocumentationUseCase` need repository-scoped retrieval, so the field was added to `RetrievalQuery` and threaded through `RetrievalService._search_fuse_and_hydrate` into both search calls — closing a real, previously-invisible gap rather than working around it.

## `search.py` / `docs.py` test scope

Both routers depend on `RetrievalService`, which needs a reachable Qdrant — none is running in this dev environment, and `RetrievalService`'s own correctness (RRF fusion, hydration, reranking) is already thoroughly proven end-to-end against real Qdrant+Postgres in Module 11's integration suite. Re-proving that here, or loading the real BGE-M3 embedding model just to drive an HTTP happy path, would either duplicate existing coverage or violate Module 9's established precedent of never loading real ML models in the automated suite. Router-level tests for `search.py`/`docs.py` are therefore scoped to the HTTP boundary only: authentication (401), workspace/repository ownership (404, anti-enumeration), and request validation (422 — `SearchRequest.limit` out of range, `GenerateDocsRequest` missing `path` for a non-repository scope). `conversations.py`'s CRUD + the full SSE happy path already have real end-to-end integration coverage (`test_conversation_routes.py`), including the real Postgres/Redis/Ollama round trip that caught the session-lifecycle bug above.

## Testing notes

- `test_search_routes.py` (3 tests), `test_docs_routes.py` (4 tests): auth/ownership/validation boundaries, no Qdrant required.
- `test_conversation_routes.py` (3 tests): full CRUD flow, cross-workspace 404, and the real SSE streaming round trip against real Postgres/Redis/Ollama.
- `test_rate_limit.py` (2 tests) + `test_auth_routes.py::test_login_is_rate_limited_per_ip`: rate limiting in isolation and wired onto a real route.
- `test_error_handling.py` (12 tests): every domain exception type maps to its documented status code; unhandled exceptions map to a generic 500 with no internals leaked.
- `test_correlation_id.py`: new regression test for the exception-path correlation-ID bug.
- `pytest -q`: 379 passed. `mypy app`: no issues, 189 source files (one narrowly-scoped `# type: ignore[arg-type]` on `add_exception_handler(DomainError, ...)` — Starlette's stub expects a bare-`Exception`-typed handler, which a `DomainError`-narrowed handler doesn't structurally satisfy despite being correct at runtime). `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No standalone manual server smoke test beyond the integration suite: `test_send_message_streams_sse_response_and_persists_both_turns` already drives the real ASGI app (real ASGI lifespan, real Postgres, real Redis, real Ollama) through a full authenticated SSE round trip, which is the load-bearing smoke test for this module's riskiest code path.
