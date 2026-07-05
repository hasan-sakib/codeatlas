from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    hashed_password: str
    full_name: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
