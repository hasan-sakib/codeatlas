import logging

import structlog
from celery import Celery

from app.core.config import Settings
from app.core.logging import configure_logging, register_celery_logging_signals


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def _make_settings() -> Settings:
    return Settings(
        environment="local",  # type: ignore[arg-type]
        database={"url": "postgresql+asyncpg://u:p@h:5432/d"},  # type: ignore[arg-type]
        qdrant={"url": "http://localhost:6333"},  # type: ignore[arg-type]
        redis={"url": "redis://localhost:6379/0"},  # type: ignore[arg-type]
        ollama={"base_url": "http://localhost:11434"},  # type: ignore[arg-type]
        security={"jwt_secret_key": "test-secret"},  # type: ignore[arg-type]
    )


def test_celery_task_logs_include_task_id_and_propagated_correlation_id() -> None:
    # Celery's task_prerun/task_postrun are process-global signals, so we
    # run entirely in Celery's "eager" mode (synchronous, in-process, no
    # broker/worker needed) — this is a unit test, not an integration
    # test, despite exercising real Celery task dispatch machinery.
    configure_logging(_make_settings())

    celery_app = Celery("test_app", broker="memory://", backend="cache+memory://")
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    register_celery_logging_signals(celery_app)

    @celery_app.task(name="test_logging_task")
    def _sample_task(correlation_id: str | None = None) -> str:
        structlog.get_logger("test.celery").info("task.running")
        return "done"

    root_logger = logging.getLogger()
    handler = _ListHandler()
    handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.addHandler(handler)
    try:
        result = _sample_task.apply_async(kwargs={"correlation_id": "propagated-cid"})
    finally:
        root_logger.removeHandler(handler)

    assert result.get() == "done"
    task_line = next(line for line in handler.lines if "task.running" in line)
    assert "propagated-cid" in task_line
    assert "task_id" in task_line


def test_celery_task_generates_correlation_id_when_not_propagated() -> None:
    configure_logging(_make_settings())

    celery_app = Celery("test_app_2", broker="memory://", backend="cache+memory://")
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    register_celery_logging_signals(celery_app)

    @celery_app.task(name="test_logging_task_no_cid")
    def _sample_task() -> str:
        structlog.get_logger("test.celery").info("task.running.no_cid")
        return "done"

    root_logger = logging.getLogger()
    handler = _ListHandler()
    handler.setFormatter(root_logger.handlers[0].formatter)
    root_logger.addHandler(handler)
    try:
        _sample_task.apply_async(kwargs={})
    finally:
        root_logger.removeHandler(handler)

    task_line = next(line for line in handler.lines if "task.running.no_cid" in line)
    assert "correlation_id" in task_line
