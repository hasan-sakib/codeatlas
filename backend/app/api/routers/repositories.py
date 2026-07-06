from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_current_user, require_workspace_access
from app.api.schemas.repository import CreateRepositoryRequest, RepositoryResponse
from app.application.use_cases.indexing.create_repository import CreateRepositoryUseCase
from app.application.use_cases.indexing.delete_repository import DeleteRepositoryUseCase
from app.application.use_cases.indexing.get_repository import GetRepositoryUseCase
from app.application.use_cases.indexing.list_repositories import ListRepositoriesUseCase
from app.core.di import (
    provide_indexing_job_repository,
    provide_indexing_task_dispatcher,
    provide_repository_repository,
)
from app.domain.entities.repository import Repository
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.domain.exceptions import RepositoryNotFoundError
from app.domain.ports.indexing_job_repository import IndexingJobRepository
from app.domain.ports.indexing_task_dispatcher import IndexingTaskDispatcherPort
from app.domain.ports.repository_repository import RepositoryRepository
from app.infrastructure.vcs.url_validator import RepositoryUrlValidationError

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/repositories", tags=["repositories"])


def _to_response(repository: Repository) -> RepositoryResponse:
    return RepositoryResponse(
        id=repository.id,
        workspace_id=repository.workspace_id,
        source_type=repository.source_type,
        git_url=repository.git_url,
        default_branch=repository.default_branch,
        local_path=repository.local_path,
        last_indexed_commit_sha=repository.last_indexed_commit_sha,
        status=repository.status,
        created_at=repository.created_at,
        updated_at=repository.updated_at,
    )


@router.post("", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(
    body: CreateRepositoryRequest,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    user: Annotated[User, Depends(require_current_user)],
    repository_repo: Annotated[RepositoryRepository, Depends(provide_repository_repository)],
    job_repo: Annotated[IndexingJobRepository, Depends(provide_indexing_job_repository)],
    task_dispatcher: Annotated[
        IndexingTaskDispatcherPort, Depends(provide_indexing_task_dispatcher)
    ],
) -> RepositoryResponse:
    use_case = CreateRepositoryUseCase(repository_repo, job_repo, task_dispatcher)
    try:
        repository = await use_case.execute(workspace.id, body.git_url, user.id)
    except RepositoryUrlValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_response(repository)


@router.get("", response_model=list[RepositoryResponse])
async def list_repositories(
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    repository_repo: Annotated[RepositoryRepository, Depends(provide_repository_repository)],
) -> list[RepositoryResponse]:
    use_case = ListRepositoriesUseCase(repository_repo)
    repositories = await use_case.execute(workspace.id)
    return [_to_response(r) for r in repositories]


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: UUID,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    repository_repo: Annotated[RepositoryRepository, Depends(provide_repository_repository)],
) -> RepositoryResponse:
    use_case = GetRepositoryUseCase(repository_repo)
    try:
        repository = await use_case.execute(workspace.id, repository_id)
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        ) from exc
    return _to_response(repository)


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: UUID,
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
    repository_repo: Annotated[RepositoryRepository, Depends(provide_repository_repository)],
) -> None:
    use_case = DeleteRepositoryUseCase(repository_repo)
    try:
        await use_case.execute(workspace.id, repository_id)
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
        ) from exc
