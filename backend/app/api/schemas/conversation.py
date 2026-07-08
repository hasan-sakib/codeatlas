from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.api.streaming.events import CitationEvent


class CreateConversationRequest(BaseModel):
    title: str | None = None


class ConversationResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    title: str | None
    summary: str | None
    turn_count: int
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    citations: list[CitationEvent]
    token_count: int
    created_at: datetime | None


class SendMessageRequest(BaseModel):
    content: str
