from typing import Protocol
from uuid import UUID


class IndexingTaskDispatcherPort(Protocol):
    async def dispatch(self, job_id: UUID) -> str:
        """Enqueue the indexing pipeline for `job_id`, returning a
        task/handle id to persist on the IndexingJob row.

        Kept abstract so CreateRepositoryUseCase doesn't hard-depend on
        Celery's wire format — the real Celery-backed adapter is registered
        once the indexing pipeline exists (see NullIndexingTaskDispatcher
        for the current placeholder).
        """
        ...
