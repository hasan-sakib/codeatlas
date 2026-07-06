import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.entities.workspace import Workspace
from app.domain.exceptions import WorkspaceSlugAlreadyExistsError
from app.domain.ports.workspace_repository import WorkspaceRepository

_SLUG_INVALID_CHARS_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _SLUG_INVALID_CHARS_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "workspace"


class CreateWorkspaceUseCase:
    def __init__(self, workspace_repo: WorkspaceRepository) -> None:
        self._workspace_repo = workspace_repo

    async def execute(self, owner_id: UUID, name: str, description: str | None = None) -> Workspace:
        slug = _slugify(name)

        # Check-then-insert has a small race window (two concurrent
        # requests for the same owner+name could both pass this check);
        # the DB's uq_workspaces_owner_slug constraint is the real
        # backstop. Accepted for v1 — a workspace-name collision is
        # low-severity and self-correctable by retry, unlike the
        # refresh-token rotation race, which needed an atomic guarantee.
        existing = await self._workspace_repo.list_for_owner(owner_id)
        if any(w.slug == slug for w in existing):
            raise WorkspaceSlugAlreadyExistsError(owner_id, slug)

        now = datetime.now(UTC)
        workspace = Workspace(
            id=uuid4(),
            owner_id=owner_id,
            name=name,
            slug=slug,
            description=description,
            created_at=now,
            updated_at=now,
        )
        return await self._workspace_repo.add(workspace)
