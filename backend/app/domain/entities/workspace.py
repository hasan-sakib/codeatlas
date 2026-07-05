from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Workspace:
    id: UUID
    owner_id: UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime
