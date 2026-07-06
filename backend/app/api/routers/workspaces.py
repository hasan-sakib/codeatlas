from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_current_user, require_workspace_access
from app.api.schemas.workspace import CreateWorkspaceRequest, WorkspaceResponse
from app.application.use_cases.workspaces.create_workspace import CreateWorkspaceUseCase
from app.application.use_cases.workspaces.list_workspaces import ListWorkspacesUseCase
from app.core.di import provide_workspace_repository
from app.domain.entities.user import User
from app.domain.entities.workspace import Workspace
from app.domain.exceptions import WorkspaceSlugAlreadyExistsError
from app.domain.ports.workspace_repository import WorkspaceRepository

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def _to_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        owner_id=workspace.owner_id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user: Annotated[User, Depends(require_current_user)],
    workspace_repo: Annotated[WorkspaceRepository, Depends(provide_workspace_repository)],
) -> WorkspaceResponse:
    use_case = CreateWorkspaceUseCase(workspace_repo)
    try:
        workspace = await use_case.execute(user.id, body.name, body.description)
    except WorkspaceSlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workspace with an equivalent name already exists",
        ) from exc
    return _to_response(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: Annotated[User, Depends(require_current_user)],
    workspace_repo: Annotated[WorkspaceRepository, Depends(provide_workspace_repository)],
) -> list[WorkspaceResponse]:
    use_case = ListWorkspacesUseCase(workspace_repo)
    workspaces = await use_case.execute(user.id)
    return [_to_response(w) for w in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace: Annotated[Workspace, Depends(require_workspace_access)],
) -> WorkspaceResponse:
    return _to_response(workspace)
