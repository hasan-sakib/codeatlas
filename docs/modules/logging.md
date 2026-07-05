# Module 3: Logging

## Processor chain

```
shared_processors = [
    structlog.contextvars.merge_contextvars,   # pulls in correlation_id/task_id
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    redact_sensitive_fields,                    # masks password/token/etc.
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]
```

These run for **every** log call — structlog-native (`structlog.get_logger()`) and stdlib (`logging.getLogger()`, e.g. uvicorn/sqlalchemy) alike — via `structlog.stdlib.ProcessorFormatter`, which bridges the two. The final renderer (`JSONRenderer` for `production`/`staging`, `ConsoleRenderer(colors=True)` otherwise) is applied once, after the shared chain, so both paths produce identical output shape.

## How to emit a log

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("workspace.created", workspace_id=str(ws.id))
```

Use an `event.name`-style string as the message (not an f-string) and pass structured fields as kwargs — this is what makes the JSON output queryable.

## Redacted keys

`password`, `token`, `access_token`, `refresh_token`, `authorization`, `jwt_secret_key`, `secret` (case-insensitive), including nested dict values. Add new ones to `SENSITIVE_KEYS` in `app/core/logging.py`.

## Correlation IDs

`CorrelationIdMiddleware` reads `X-Request-ID` (or generates a UUID4), binds it via `bind_correlation_id()`, and echoes it back in the response header. Any log call anywhere during that request automatically includes `correlation_id` via `merge_contextvars` — no need to pass it explicitly.

For Celery tasks, call `register_celery_logging_signals(celery_app)` once at worker startup. It binds `task_id` and propagates `correlation_id` if the caller passed it as a task kwarg (e.g. `some_task.delay(correlation_id=get_correlation_id(), ...)`); otherwise a fresh one is generated.

## Real bugs found while building this (not just design-doc theory)

1. **`cache_logger_on_first_use=True` + module-level loggers don't mix with dynamic reconfiguration.** A `logger = structlog.get_logger(__name__)` created at module import time permanently binds to whatever structlog config was active on its *first* log call. Any later `configure_logging()` call (e.g. a second `create_app()` in a different test) is silently ignored by already-fired loggers. Fixed by setting `cache_logger_on_first_use=False` — every log call re-resolves against the current global config.

2. **`CorrelationIdMiddleware` must be plain ASGI, not `BaseHTTPMiddleware`.** `BaseHTTPMiddleware` runs the downstream app in a separate `anyio` task (`TaskGroup.start_soon`) to support streaming responses. Contextvars set before `call_next()` don't propagate into that spawned task, so `correlation_id` bound in the middleware never appeared in route-handler logs. Confirmed by tracing `structlog.contextvars.get_contextvars()` immediately after binding (present) vs. inside the route handler (absent) with the `BaseHTTPMiddleware` version. Fixed by rewriting as a plain ASGI middleware class (`__init__(self, app)` / `async def __call__(self, scope, receive, send)`), which awaits the downstream app in the *same* coroutine — no task boundary, so contextvars flow through correctly.

3. **`structlog.testing.capture_logs()` cannot see contextvar-bound fields.** Reading its actual source: it replaces the entire processor list with just `[LogCapture()]`, deliberately excluding `merge_contextvars`. It's the wrong tool for testing correlation-id propagation — use a real `logging.Handler` (or `capsys`/`caplog`, with care around thread/capture ordering) against the actual configured pipeline instead.

## Testing notes

- `TestClient` runs the ASGI app in a background thread (anyio blocking portal). This fights with `capsys` if a handler already captured a `sys.stdout` reference before `capsys` swapped it — reorder fixture params (`capsys` before `client`) or, more robustly, attach a `logging.Handler` directly (thread-safe regardless of emission order) as `test_correlation_id.py` does.
- The Celery signal test runs in `task_always_eager=True` mode (in-process, no broker) — classified as a unit test here despite exercising real Celery dispatch, since it needs no external infrastructure.
