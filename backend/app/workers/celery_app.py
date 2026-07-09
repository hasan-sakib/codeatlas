import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from celery import Celery
from celery.signals import worker_init

_T = TypeVar("_T")

# Bare instance at import time — deliberately reads no settings here.
# Tests (and other app code) import this module, or app.workers.tasks.*
# which needs `celery_app` to decorate task functions, transitively and
# often before any test fixture has set the env vars Settings() requires
# — an eager `get_settings()` call at module scope broke exactly that
# (verified directly: importing this module with no env vars raised
# immediately). Real settings (broker_url/result_backend/logging) are
# applied lazily via `ensure_configured()`, called both by the actual
# Celery worker process (via the worker_init signal below) and by
# CeleryIndexingTaskDispatcher before every dispatch from the API
# process — the two processes that ever need a real broker connection.
celery_app = Celery("codeatlas")
celery_app.conf.update(
    task_routes={"indexing.*": {"queue": "indexing"}},
    task_track_started=True,
    # A clone+parse+chunk+embed+upsert run can legitimately take minutes
    # for a real repository — no default time limit.
    task_time_limit=None,
)

_configured = False


def ensure_configured() -> Celery:
    global _configured
    if not _configured:
        from app.core.config import get_settings
        from app.core.logging import configure_logging, register_celery_logging_signals

        settings = get_settings()
        configure_logging(settings)
        celery_app.conf.broker_url = str(settings.celery.broker_url)
        celery_app.conf.result_backend = str(settings.celery.result_backend)
        register_celery_logging_signals(celery_app)
        _configured = True
    return celery_app


@worker_init.connect(weak=False)  # type: ignore[untyped-decorator]
def _configure_on_worker_start(**_: object) -> None:
    ensure_configured()


_worker_loop: asyncio.AbstractEventLoop | None = None


def run_in_worker_loop(coro_fn: Callable[[], Awaitable[_T]]) -> _T:
    """Runs `coro_fn()` on one event loop kept alive for this worker
    process's entire lifetime, instead of `asyncio.run()`'s default of a
    brand-new loop per call.

    Every process-wide cached async resource in this codebase — the
    SQLAlchemy async engine's connection pool (`app.infrastructure.db.
    session`), the Redis client, the Qdrant client — binds its
    connections to whichever event loop was running when it was first
    used, and asyncpg/redis-py connections cannot cross event loops.
    Celery's prefork worker reuses one child process across many task
    executions; `asyncio.run()` per task would tear down and recreate
    the loop every time while those cached resources kept referencing
    connections from the now-closed loop — verified directly: a second
    task in the same worker process failed with "attached to a
    different loop" on its very first DB query. One persistent
    per-process loop keeps every cached resource valid for as long as
    the worker process lives, matching how a single long-lived FastAPI
    process's one event loop already works.
    """
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop.run_until_complete(coro_fn())


# Populates app.workers.tasks.indexing_tasks's @celery_app.task
# registrations — safe at import time since task definition itself
# needs no settings, only the bare `celery_app` instance above.
celery_app.autodiscover_tasks(["app.workers"])
