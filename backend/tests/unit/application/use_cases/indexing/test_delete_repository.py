from uuid import uuid4

import pytest

from app.application.use_cases.indexing.create_repository import CreateRepositoryUseCase
from app.application.use_cases.indexing.delete_repository import DeleteRepositoryUseCase
from app.domain.exceptions import RepositoryNotFoundError
from tests.unit.application.use_cases.indexing.fakes import (
    FakeIndexingJobRepository,
    FakeIndexingTaskDispatcher,
    FakeRepositoryRepository,
)


async def test_delete_repository_removes_it() -> None:
    repo_repo = FakeRepositoryRepository()
    create = CreateRepositoryUseCase(
        repo_repo, FakeIndexingJobRepository(), FakeIndexingTaskDispatcher()
    )
    workspace_id = uuid4()
    repository = await create.execute(workspace_id, "https://github.com/org/repo.git", uuid4())

    await DeleteRepositoryUseCase(repo_repo).execute(workspace_id, repository.id)

    assert repository.id not in repo_repo.repositories


async def test_delete_repository_raises_not_found_for_wrong_workspace() -> None:
    repo_repo = FakeRepositoryRepository()
    create = CreateRepositoryUseCase(
        repo_repo, FakeIndexingJobRepository(), FakeIndexingTaskDispatcher()
    )
    repository = await create.execute(uuid4(), "https://github.com/org/repo.git", uuid4())

    with pytest.raises(RepositoryNotFoundError):
        await DeleteRepositoryUseCase(repo_repo).execute(uuid4(), repository.id)

    assert repository.id in repo_repo.repositories
