from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.domain.entities.indexing_job import IndexingJobStatus
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


class IndexingJobResponse(BaseModel):
    id: UUID
    repository_id: UUID
    celery_task_id: str | None
    status: IndexingJobStatus
    stage_detail: str | None
    files_total: int
    files_processed: int
    chunks_total: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
