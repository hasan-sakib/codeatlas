from uuid import uuid4

import pytest

from app.application.use_cases.workspaces.create_workspace import CreateWorkspaceUseCase
from app.domain.exceptions import WorkspaceSlugAlreadyExistsError
from tests.unit.application.use_cases.workspaces.fakes import FakeWorkspaceRepository


async def test_create_workspace_slugifies_name() -> None:
    repo = FakeWorkspaceRepository()
    owner_id = uuid4()
    use_case = CreateWorkspaceUseCase(repo)

    workspace = await use_case.execute(owner_id, "My Cool Project!!", description="desc")

    assert workspace.slug == "my-cool-project"
    assert workspace.owner_id == owner_id
    assert workspace.description == "desc"


async def test_create_workspace_rejects_duplicate_slug_for_same_owner() -> None:
    repo = FakeWorkspaceRepository()
    owner_id = uuid4()
    use_case = CreateWorkspaceUseCase(repo)
    await use_case.execute(owner_id, "My Project")

    with pytest.raises(WorkspaceSlugAlreadyExistsError):
        await use_case.execute(owner_id, "My Project")


async def test_create_workspace_allows_same_name_for_different_owners() -> None:
    repo = FakeWorkspaceRepository()
    use_case = CreateWorkspaceUseCase(repo)

    a = await use_case.execute(uuid4(), "Shared Name")
    b = await use_case.execute(uuid4(), "Shared Name")

    assert a.slug == b.slug == "shared-name"
    assert a.owner_id != b.owner_id
