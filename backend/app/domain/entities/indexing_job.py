from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class IndexingJobStatus(str, Enum):
    QUEUED = "queued"
    CLONING = "cloning"
    WALKING = "walking"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    UPSERTING = "upserting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class IndexingJob:
    id: UUID
    repository_id: UUID
    celery_task_id: str | None
    status: IndexingJobStatus
    stage_detail: str | None
    files_total: int
    files_processed: int
    chunks_total: int
    error_message: str | None
    retry_count: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
