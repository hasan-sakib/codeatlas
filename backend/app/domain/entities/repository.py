from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class RepositorySourceType(str, Enum):
    GIT_URL = "git_url"
    UPLOAD_ZIP = "upload_zip"


class RepositoryStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class Repository:
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
