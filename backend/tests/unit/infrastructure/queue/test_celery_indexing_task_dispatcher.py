from uuid import uuid4

import pytest

from app.infrastructure.queue.celery_indexing_task_dispatcher import (
    CeleryIndexingTaskDispatcher,
)
from app.workers.celery_app import celery_app


async def test_dispatch_sends_the_indexing_task_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.infrastructure.queue.celery_indexing_task_dispatcher.ensure_configured",
        lambda: celery_app,
    )
    sent = []

    class _FakeResult:
        id = "fake-task-id"

    def _fake_send_task(name: str, args: list[object]) -> _FakeResult:
        sent.append((name, args))
        return _FakeResult()

    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)

    dispatcher = CeleryIndexingTaskDispatcher()
    job_id = uuid4()
    task_id = await dispatcher.dispatch(job_id)

    assert task_id == "fake-task-id"
    assert sent == [("indexing.index_repository", [str(job_id)])]
