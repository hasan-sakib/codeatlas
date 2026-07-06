from uuid import uuid4

import pytest

from app.application.use_cases.indexing.create_repository import CreateRepositoryUseCase
from app.domain.entities.repository import RepositoryStatus
from app.infrastructure.vcs.url_validator import RepositoryUrlValidationError
from tests.unit.application.use_cases.indexing.fakes import (
    FakeIndexingJobRepository,
    FakeIndexingTaskDispatcher,
    FakeRepositoryRepository,
)


async def test_create_repository_persists_repository_and_queues_job() -> None:
    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    dispatcher = FakeIndexingTaskDispatcher()
    use_case = CreateRepositoryUseCase(repo_repo, job_repo, dispatcher)
    workspace_id = uuid4()
    user_id = uuid4()

    repository = await use_case.execute(workspace_id, "https://github.com/org/repo.git", user_id)

    assert repository.workspace_id == workspace_id
    assert repository.status == RepositoryStatus.INDEXING
    assert repo_repo.repositories[repository.id].status == RepositoryStatus.INDEXING
    assert job_repo.add_call_count == 1
    (job,) = job_repo.jobs.values()
    assert job.repository_id == repository.id
    assert job.celery_task_id == f"fake-task-{job.id}"
    assert dispatcher.dispatched == [job.id]


async def test_create_repository_rejects_invalid_url_without_persisting() -> None:
    repo_repo = FakeRepositoryRepository()
    job_repo = FakeIndexingJobRepository()
    dispatcher = FakeIndexingTaskDispatcher()
    use_case = CreateRepositoryUseCase(repo_repo, job_repo, dispatcher)

    with pytest.raises(RepositoryUrlValidationError):
        await use_case.execute(uuid4(), "file:///etc/passwd", uuid4())

    assert repo_repo.repositories == {}
    assert job_repo.jobs == {}
    assert dispatcher.dispatched == []
