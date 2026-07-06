from uuid import uuid4

import pytest

from app.application.use_cases.workspaces.create_workspace import CreateWorkspaceUseCase
from app.application.use_cases.workspaces.get_workspace import GetWorkspaceUseCase
from app.domain.exceptions import WorkspaceNotFoundError
from tests.unit.application.use_cases.workspaces.fakes import FakeWorkspaceRepository


async def test_get_workspace_returns_workspace_for_owner() -> None:
    repo = FakeWorkspaceRepository()
    owner_id = uuid4()
    workspace = await CreateWorkspaceUseCase(repo).execute(owner_id, "Mine")

    result = await GetWorkspaceUseCase(repo).execute(workspace.id, owner_id)

    assert result.id == workspace.id


async def test_get_workspace_raises_not_found_for_unknown_id() -> None:
    repo = FakeWorkspaceRepository()

    with pytest.raises(WorkspaceNotFoundError):
        await GetWorkspaceUseCase(repo).execute(uuid4(), uuid4())


async def test_get_workspace_raises_not_found_for_non_owner() -> None:
    repo = FakeWorkspaceRepository()
    owner_id = uuid4()
    workspace = await CreateWorkspaceUseCase(repo).execute(owner_id, "Mine")

    with pytest.raises(WorkspaceNotFoundError):
        await GetWorkspaceUseCase(repo).execute(workspace.id, uuid4())
