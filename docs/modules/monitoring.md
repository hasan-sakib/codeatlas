# Module 20: Monitoring

## Purpose

Give the running system observability: Prometheus metrics (`/metrics`), liveness/readiness health checks (`/health/live`, `/health/ready`), and instrumentation of real, already-built call sites — without touching agent/LLM/retrieval logic itself. The final module; nothing downstream depends on it.

## What already existed vs. what this module built

`app/api/routers/health.py` already had a bare `/health` (Module 1) — kept unchanged for backward compatibility. `retrieval_service.py`'s own docstring already anticipated this module by name ("Emits retrieval timing via structlog rather than a `retrieval_duration_seconds` Prometheus metric — Module 20 doesn't exist yet"), which is exactly where instrumentation was added. No Prometheus dependency, `app/core/observability/`, or health-check-beyond-liveness existed anywhere before this module.

## Architecture

- `app/core/observability/metrics.py` — module-level Prometheus singletons: `retrieval_duration_seconds` (Histogram, `stage=dense|sparse|fuse|rerank`), `llm_tokens_total` (Counter, `direction=prompt|completion`), `cache_hits_total`/`cache_misses_total` (Counter, `cache_name`).
- `app/core/observability/instrumentation.py` — `setup_prometheus_instrumentator(app)`, wraps `prometheus-fastapi-instrumentator` for the automatic `http_request_duration_seconds`/`http_requests_total` family.
- `app/core/observability/health_checks.py` — `DependencyStatus` + `check_postgres`/`check_redis`/`check_qdrant`/`check_ollama`/`check_all_dependencies`. None of these call an existing port method — no port exposes anything cheap enough for a readiness probe (`LLMPort.complete()`/`VectorStorePort.search_*()` all do real work), so each check goes directly against the lightest real operation available: `SELECT 1` via a fresh `db_session_context()`, `Redis.ping()`, Qdrant's `get_collections()`, and a raw `GET {OLLAMA__BASE_URL}/api/tags` (bypassing `OllamaAdapter` entirely, since it has no method this cheap).
- `app/api/routers/health.py` — `/health/live` (unconditional 200, deliberately never calls dependency checks) and `/health/ready` (runs all four checks concurrently via `asyncio.gather`, 503 if any fail, itemized body always included).

## A small rename: `_get_qdrant_client` → `provide_qdrant_client`

`core/di.py`'s Qdrant client provider was private (leading underscore), used only internally by `provide_vector_store()`. `check_qdrant()` needed the same cached singleton client for its own lightweight `get_collections()` call — reusing a private name across module boundaries is the wrong shape for what's now a second legitimate caller, so it was renamed to match every other `provide_*` DI function in that file. No behavior change; `clear_vector_store_cache()`'s reference was updated in the same edit.

## Design decisions

- **`retrieval_duration_seconds` labels exactly `dense|sparse|fuse|rerank`**, matching the design's own stated label enumeration precisely rather than expanding to `embed`/`hydration` — those stay covered by the existing `retrieval.completed` structlog line's `duration_seconds` field only. Dense and sparse run concurrently via `asyncio.gather` in `_search_fuse_and_hydrate`, so each got its own inline timer wrapping the individual coroutine *before* `gather` schedules them — timing the `gather` call itself would have measured wall-clock overlap, not each stage's real cost.
- **`indexing_job_duration_seconds`/`celery_queue_depth` are defined but have no live call site** — the Background Jobs / Queue Infrastructure module was never built (`worker` is still a `sleep infinity` placeholder; `IndexingTaskDispatcherPort`'s only implementation is `NullIndexingTaskDispatcher`). Defined now so the eventual indexing pipeline has metrics to emit into from day one, documented in `metrics.py` itself as a forward-dependency gap rather than fabricated usage against a made-up call site.
- **No `workers/health_cli.py`** — the design calls for a Celery-ping-based CLI health check for the worker process, but there's no real Celery app to ping. Building one now would mean testing against nothing real. Deferred to whichever module actually builds the indexing pipeline.
- **`stream_complete()` now captures token counts from Ollama's final NDJSON line** (`done: true`) — previously it discarded every field except `response` text. `complete()` already parsed `prompt_eval_count`/`eval_count`; extending the streaming path to do the same (rather than leaving `llm_tokens_total` blind to the one call path actually used by real chat) is completing already-partially-built functionality using fields Ollama already sends, not new scope.
- **`docker-compose.yml`'s `backend-api` healthcheck now targets `/health/ready`, not `/health`** — this was DESIGN.md §22's healthcheck matrix all along ("backend-api: `GET /health/ready` (checks DB, Redis, Qdrant, Ollama reachability)"), just unimplemented until `/health/ready` existed. `interval`/`timeout`/`retries`/`start_period` were all widened at the same time: the bare-liveness healthcheck this replaces never needed to tolerate Module 19's embedding-model warm-up blocking the server from accepting connections at all; `/health/ready` genuinely checking four dependencies needs more headroom than the previous 3s timeout allowed.

## Verified live, against a real Docker Compose stack

Brought up the full dev-overlay stack (all 7 services) and drove real traffic through the actual running server, not just unit tests with mocks:

- `/health/ready` returned real per-dependency latencies (43–50ms each) for all four checks. Stopping the `redis` container mid-session made it return `503` with `{"name": "redis", "healthy": false, "detail": "Error -2 connecting to redis:6379..."}` while Postgres/Qdrant/Ollama stayed reported healthy — confirmed independence between checks, not just an all-or-nothing gate. Restarting Redis recovered to `200` within seconds.
- A real `POST /search` call against an empty (but real) Qdrant collection produced genuine `retrieval_duration_seconds` samples for the `dense`/`sparse` stages, visible on `/metrics`, and a real `cache_misses_total{cache_name="embedding"}` increment from the query's never-before-seen embedding.
- A real chat call eventually reached Ollama's `/api/generate` and produced a genuine `llm_tokens_total{direction="prompt"}`/`{direction="completion"}` reading on `/metrics` — see the note below on why "eventually."
- `http_request_duration_seconds` correctly excluded the SSE endpoint's full streaming lifetime: despite individual chat requests staying open 30+ seconds, the recorded metric sum across 6 requests was ~3.9 seconds total — confirming `should_exclude_streaming_duration=True` measures time-to-first-byte, not full stream duration, exactly as intended.

**A red herring chased down and ruled out, not silently ignored**: several live chat attempts hit Module 16's 30-second SSE idle-timeout with zero tokens streamed. Isolated `OllamaAdapter.complete()` and `.stream_complete()` calls directly (bypassing the agent graph) both completed in seconds with correct output and correctly incremented `llm_tokens_total` — ruling out this module's adapter changes. `docker stats` during a hung attempt showed the `ollama` container pegged at 900–1800% CPU, genuinely computing, not deadlocked. Conclusion: real CPU-only Qwen3 thinking-mode inference, on a Docker Desktop VM sharing this session's heavily-loaded host, occasionally exceeds 30 seconds before emitting a token — a pre-existing, already-documented characteristic of this model/environment combination (see `ollama_adapter.py`'s own docstring on thinking-mode token unpredictability), not a Module 20 regression. Tuning the idle-timeout for slow-CPU environments is a legitimate follow-up but belongs to Module 16, not this one.

## Testing notes

- `tests/unit/core/observability/test_health_checks.py` (12 tests): each check function healthy/unhealthy/(postgres also timeout), plus `check_all_dependencies` running all four.
- `tests/unit/core/observability/test_instrumentation.py` (2 tests): `/metrics` actually exposed and populated after a real request; `/metrics` excluded from the OpenAPI schema.
- `tests/unit/test_health_endpoint.py`: extended with liveness-never-calls-dependencies (mocked to raise if it did), readiness 200-when-healthy and 503-when-one-unhealthy with itemized body.
- `tests/unit/application/services/test_retrieval_service.py`: new test asserting all four stage labels (`dense`/`sparse`/`fuse`/`rerank`) each get exactly one observation per `retrieve()` call, via `prometheus_client.REGISTRY.get_sample_value` before/after deltas (the standard way to test global Prometheus counters without asserting absolute values against a registry shared by the whole test session).
- `tests/unit/infrastructure/llm/test_ollama_adapter.py`: two new tests — `llm_tokens_total` increments correctly from `complete()`, and from `stream_complete()`'s final `done: true` chunk specifically (not from any intermediate chunk).
- `tests/integration/infrastructure/embeddings/test_embedding_cache.py`: new test asserting one hit and one miss increment correctly from a single `get_many()` call against real Redis.
- Full suite: `402 passed`. `mypy app`: clean, 193 source files. `ruff`/`black`/`pre-commit run --all-files`: clean.
