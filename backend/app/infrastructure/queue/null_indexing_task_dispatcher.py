from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class NullIndexingTaskDispatcher:
    """Placeholder `IndexingTaskDispatcherPort` — no Celery worker/broker
    exists yet (the indexing pipeline modules haven't landed).

    Persists no state and enqueues nothing; it exists only so
    CreateRepositoryUseCase has something to call today. Every call logs a
    warning so this is never mistaken for a working queue integration.
    Replace with a real Celery-backed adapter once the indexing pipeline
    is implemented.
    """

    async def dispatch(self, job_id: UUID) -> str:
        logger.warning(
            "indexing_task_dispatch.not_implemented",
            job_id=str(job_id),
            detail="No queue is wired up yet — this job will never actually run.",
        )
        return f"noop-{job_id}"
