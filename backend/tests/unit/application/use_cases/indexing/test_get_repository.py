from uuid import uuid4

import pytest

from app.application.use_cases.indexing.create_repository import CreateRepositoryUseCase
from app.application.use_cases.indexing.get_repository import GetRepositoryUseCase
from app.domain.exceptions import RepositoryNotFoundError
from tests.unit.application.use_cases.indexing.fakes import (
    FakeIndexingJobRepository,
    FakeIndexingTaskDispatcher,
    FakeRepositoryRepository,
)


async def test_get_repository_returns_repository_in_workspace() -> None:
    repo_repo = FakeRepositoryRepository()
    create = CreateRepositoryUseCase(
        repo_repo, FakeIndexingJobRepository(), FakeIndexingTaskDispatcher()
    )
    workspace_id = uuid4()
    repository = await create.execute(workspace_id, "https://github.com/org/repo.git", uuid4())

    result = await GetRepositoryUseCase(repo_repo).execute(workspace_id, repository.id)

    assert result.id == repository.id


async def test_get_repository_raises_not_found_for_wrong_workspace() -> None:
    repo_repo = FakeRepositoryRepository()
    create = CreateRepositoryUseCase(
        repo_repo, FakeIndexingJobRepository(), FakeIndexingTaskDispatcher()
    )
    repository = await create.execute(uuid4(), "https://github.com/org/repo.git", uuid4())

    with pytest.raises(RepositoryNotFoundError):
        await GetRepositoryUseCase(repo_repo).execute(uuid4(), repository.id)


async def test_get_repository_raises_not_found_for_unknown_id() -> None:
    repo_repo = FakeRepositoryRepository()

    with pytest.raises(RepositoryNotFoundError):
        await GetRepositoryUseCase(repo_repo).execute(uuid4(), uuid4())
