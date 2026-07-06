from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str | None = None


class WorkspaceResponse(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime
