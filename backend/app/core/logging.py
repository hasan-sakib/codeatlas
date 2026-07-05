import logging
import sys
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from app.core.config import Settings

if TYPE_CHECKING:
    from celery import Celery

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "jwt_secret_key",
        "secret",
    }
)

_REDACTED = "***REDACTED***"

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_celery_signals_registered = False


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (_REDACTED if key.lower() in SENSITIVE_KEYS else _redact_value(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact_sensitive_fields(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    return {
        key: (_REDACTED if key.lower() in SENSITIVE_KEYS else _redact_value(value))
        for key, value in event_dict.items()
    }


def configure_logging(settings: Settings) -> None:
    """Configure structlog and bridge stdlib `logging` through the same
    processor chain, so third-party libraries (uvicorn, sqlalchemy, celery)
    render identically to structlog-native log calls.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_sensitive_fields,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if settings.environment in {"production", "staging"}:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # False so module-level `logger = structlog.get_logger(__name__)`
        # singletons always reflect the latest configure_logging() call
        # instead of permanently binding to whatever was active on their
        # first-ever log call (this bit us in testing: a logger that fired
        # once before capture_logs() ran stayed bound to the old renderer
        # for the rest of the process).
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)


def bind_correlation_id(correlation_id: str | None = None) -> str:
    cid = correlation_id or str(uuid4())
    correlation_id_var.set(cid)
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    return cid


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


def clear_correlation_id() -> None:
    correlation_id_var.set(None)
    structlog.contextvars.unbind_contextvars("correlation_id")


def register_celery_logging_signals(celery_app: "Celery") -> None:
    """Bind a correlation id (propagated via task kwargs, or freshly
    generated) and the Celery task_id into every log line emitted during
    that task's execution.

    Celery's task_prerun/task_postrun are process-global signals (not
    scoped to a specific app instance); `celery_app` is accepted to match
    the call site's intent ("register logging for this app's tasks") and
    to keep this function idempotent per-process.
    """
    global _celery_signals_registered
    if _celery_signals_registered:
        return

    from celery.signals import task_postrun, task_prerun

    # celery has no py.typed marker, so .connect() is untyped from mypy's
    # perspective, which makes the decorated function look untyped too.
    @task_prerun.connect(weak=False)  # type: ignore[untyped-decorator]
    def _bind_task_context(
        task_id: str | None = None,
        kwargs: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        propagated = (kwargs or {}).get("correlation_id")
        bind_correlation_id(propagated)
        structlog.contextvars.bind_contextvars(task_id=task_id)

    @task_postrun.connect(weak=False)  # type: ignore[untyped-decorator]
    def _clear_task_context(**_: Any) -> None:
        clear_correlation_id()
        structlog.contextvars.unbind_contextvars("task_id")

    _celery_signals_registered = True
