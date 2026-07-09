from uuid import uuid4

import pytest

from app.workers.celery_app import celery_app


def test_index_repository_task_is_registered_on_the_indexing_queue() -> None:
    # Deliberately imports the *package* (`app.workers.tasks`), not the
    # `indexing_tasks` submodule directly — this is exactly what
    # `celery_app.autodiscover_tasks(["app.workers"])` does at real worker
    # startup: it imports `app.workers.tasks` and nothing beneath it on
    # its own. A version of this test that imported `indexing_tasks`
    # directly passed even when `app/workers/tasks/__init__.py` was empty
    # and a real worker registered zero tasks — this form catches that.
    import app.workers.tasks  # noqa: F401

    assert "indexing.index_repository" in celery_app.tasks
    routes = celery_app.conf.task_routes
    assert routes["indexing.*"] == {"queue": "indexing"}


def test_index_repository_task_bridges_sync_celery_call_into_async_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The task body is a thin sync-to-async bridge (`ensure_configured()`
    then `asyncio.run(_run(job_id))`) — real DB/embedding/git infra is
    exercised by RunIndexingPipelineUseCase's own unit tests, not here.
    This only proves the bridge itself: eager Celery invocation reaches
    `_run` with the correct UUID, without needing a broker or real
    infrastructure."""
    import app.workers.tasks.indexing_tasks as indexing_tasks_module

    received_job_ids = []

    async def _fake_run(job_id: object) -> None:
        received_job_ids.append(job_id)

    monkeypatch.setattr(indexing_tasks_module, "_run", _fake_run)
    monkeypatch.setattr(indexing_tasks_module, "ensure_configured", lambda: None)

    celery_app.conf.task_always_eager = True
    try:
        job_id = uuid4()
        indexing_tasks_module.index_repository_task.delay(str(job_id))
    finally:
        celery_app.conf.task_always_eager = False

    assert received_job_ids == [job_id]
