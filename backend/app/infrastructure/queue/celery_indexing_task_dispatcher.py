from uuid import UUID

from app.workers.celery_app import ensure_configured


class CeleryIndexingTaskDispatcher:
    """Real `IndexingTaskDispatcherPort` — enqueues onto the `indexing`
    Celery queue. Replaces `NullIndexingTaskDispatcher` now that
    `app/workers/tasks/indexing_tasks.py` exists to consume the task.
    """

    async def dispatch(self, job_id: UUID) -> str:
        celery_app = ensure_configured()
        result = celery_app.send_task("indexing.index_repository", args=[str(job_id)])
        return str(result.id)
