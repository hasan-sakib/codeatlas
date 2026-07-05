from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class File:
    id: UUID
    repository_id: UUID
    path: str
    language: str | None
    size_bytes: int
    content_hash: str
    last_commit_sha: str | None
    last_modified_at: datetime | None
    is_deleted: bool
    indexed_at: datetime | None
