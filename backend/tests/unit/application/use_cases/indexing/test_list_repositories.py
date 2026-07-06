from uuid import uuid4

from app.application.use_cases.indexing.create_repository import CreateRepositoryUseCase
from app.application.use_cases.indexing.list_repositories import ListRepositoriesUseCase
from tests.unit.application.use_cases.indexing.fakes import (
    FakeIndexingJobRepository,
    FakeIndexingTaskDispatcher,
    FakeRepositoryRepository,
)


async def test_list_repositories_scoped_to_workspace() -> None:
    repo_repo = FakeRepositoryRepository()
    create = CreateRepositoryUseCase(
        repo_repo, FakeIndexingJobRepository(), FakeIndexingTaskDispatcher()
    )
    workspace_a, workspace_b = uuid4(), uuid4()
    await create.execute(workspace_a, "https://github.com/org/a.git", uuid4())
    await create.execute(workspace_b, "https://github.com/org/b.git", uuid4())

    result = await ListRepositoriesUseCase(repo_repo).execute(workspace_a)

    assert len(result) == 1
    assert result[0].workspace_id == workspace_a
