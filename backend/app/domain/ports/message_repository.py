from typing import Protocol
from uuid import UUID

from app.domain.entities.message import Message


class MessageRepository(Protocol):
    async def append(self, message: Message) -> Message: ...
    async def list_recent(self, conversation_id: UUID, limit: int) -> list[Message]: ...
