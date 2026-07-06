from uuid import uuid4

from app.application.use_cases.workspaces.create_workspace import CreateWorkspaceUseCase
from app.application.use_cases.workspaces.list_workspaces import ListWorkspacesUseCase
from tests.unit.application.use_cases.workspaces.fakes import FakeWorkspaceRepository


async def test_list_workspaces_returns_only_owners_workspaces() -> None:
    repo = FakeWorkspaceRepository()
    owner_a, owner_b = uuid4(), uuid4()
    create = CreateWorkspaceUseCase(repo)
    await create.execute(owner_a, "A1")
    await create.execute(owner_a, "A2")
    await create.execute(owner_b, "B1")

    result = await ListWorkspacesUseCase(repo).execute(owner_a)

    assert {w.name for w in result} == {"A1", "A2"}
