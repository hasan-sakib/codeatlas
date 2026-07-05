from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass(frozen=True)
class Citation:
    chunk_id: UUID
    file_path: str
    start_line: int
    end_line: int
    score: float


@dataclass(frozen=True)
class Message:
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    citations: list[Citation] = field(default_factory=list)
    token_count: int = 0
    created_at: datetime | None = None
