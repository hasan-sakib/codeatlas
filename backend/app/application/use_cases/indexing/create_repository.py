from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

from app.domain.entities.indexing_job import IndexingJob, IndexingJobStatus
from app.domain.entities.repository import Repository, RepositorySourceType, RepositoryStatus
from app.domain.ports.indexing_job_repository import IndexingJobRepository
from app.domain.ports.indexing_task_dispatcher import IndexingTaskDispatcherPort
from app.domain.ports.repository_repository import RepositoryRepository
from app.infrastructure.vcs.url_validator import validate_repository_url

logger = structlog.get_logger(__name__)


class CreateRepositoryUseCase:
    """Registers a repository and immediately queues its first indexing
    job. Only performs the cheap scheme/format URL check here (fail fast
    before persisting anything) — see url_validator.py for why the
    authoritative DNS/private-IP check is deferred to actual clone time.
    """

    def __init__(
        self,
        repository_repo: RepositoryRepository,
        job_repo: IndexingJobRepository,
        task_dispatcher: IndexingTaskDispatcherPort,
    ) -> None:
        self._repository_repo = repository_repo
        self._job_repo = job_repo
        self._task_dispatcher = task_dispatcher

    async def execute(self, workspace_id: UUID, git_url: str, requested_by: UUID) -> Repository:
        validate_repository_url(git_url)

        now = datetime.now(UTC)
        repository = await self._repository_repo.add(
            Repository(
                id=uuid4(),
                workspace_id=workspace_id,
                source_type=RepositorySourceType.GIT_URL,
                git_url=git_url,
                default_branch=None,
                local_path=None,
                last_indexed_commit_sha=None,
                status=RepositoryStatus.PENDING,
                created_at=now,
                updated_at=now,
            )
        )

        job = await self._job_repo.add(
            IndexingJob(
                id=uuid4(),
                repository_id=repository.id,
                celery_task_id=None,
                status=IndexingJobStatus.QUEUED,
                stage_detail=None,
                files_total=0,
                files_processed=0,
                chunks_total=0,
                error_message=None,
                retry_count=0,
                started_at=None,
                finished_at=None,
                created_at=now,
            )
        )
        task_id = await self._task_dispatcher.dispatch(job.id)
        await self._job_repo.update(replace(job, celery_task_id=task_id))

        await self._repository_repo.update_status(repository.id, RepositoryStatus.INDEXING)

        logger.info(
            "repository.registered",
            workspace_id=str(workspace_id),
            repository_id=str(repository.id),
            job_id=str(job.id),
            requested_by=str(requested_by),
        )
        return replace(repository, status=RepositoryStatus.INDEXING)
