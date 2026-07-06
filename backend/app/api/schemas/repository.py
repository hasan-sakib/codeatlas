from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.entities.repository import RepositorySourceType, RepositoryStatus


class CreateRepositoryRequest(BaseModel):
    git_url: str


class RepositoryResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    source_type: RepositorySourceType
    git_url: str | None
    default_branch: str | None
    local_path: str | None
    last_indexed_commit_sha: str | None
    status: RepositoryStatus
    created_at: datetime
    updated_at: datetime
