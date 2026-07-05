from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Conversation:
    id: UUID
    workspace_id: UUID
    user_id: UUID
    title: str | None
    summary: str | None
    # turn_count/is_deleted aren't in DESIGN.md §14's column list, but
    # Module 15 (Conversation Service)'s ConversationRepositoryPort design
    # requires increment_turn_count() and soft_delete() — added here now
    # rather than as an awkward later migration.
    turn_count: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
