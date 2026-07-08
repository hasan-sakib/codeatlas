from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import UUID

from app.domain.entities.conversation import Conversation
from app.domain.entities.message import Message
from app.domain.exceptions import ConversationNotFoundError
from app.domain.value_objects.llm_completion_result import LLMCompletionResult


class FakeConversationRepository:
    def __init__(self, conversations: list[Conversation] | None = None) -> None:
        self.conversations: dict[UUID, Conversation] = {c.id: c for c in (conversations or [])}
        self.update_summary_calls: list[tuple[UUID, str]] = []

    async def add(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.id] = conversation
        return conversation

    async def get_by_id(self, conversation_id: UUID) -> Conversation | None:
        return self.conversations.get(conversation_id)

    async def list_for_user(
        self, user_id: UUID, workspace_id: UUID | None, limit: int, offset: int
    ) -> list[Conversation]:
        raise NotImplementedError

    async def update_summary(self, conversation_id: UUID, summary: str) -> None:
        self.update_summary_calls.append((conversation_id, summary))
        existing = self.conversations.get(conversation_id)
        if existing is not None:
            self.conversations[conversation_id] = replace(existing, summary=summary)

    async def increment_turn_count(self, conversation_id: UUID) -> int:
        existing = self.conversations.get(conversation_id)
        if existing is None:
            raise ConversationNotFoundError(conversation_id)
        updated = replace(existing, turn_count=existing.turn_count + 1)
        self.conversations[conversation_id] = updated
        return updated.turn_count

    async def soft_delete(self, conversation_id: UUID) -> None:
        existing = self.conversations.get(conversation_id)
        if existing is not None:
            self.conversations[conversation_id] = replace(existing, is_deleted=True)


class FakeMessageRepository:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def append(self, message: Message) -> Message:
        self.messages.append(message)
        return message

    async def list_recent(self, conversation_id: UUID, limit: int) -> list[Message]:
        matching = [m for m in self.messages if m.conversation_id == conversation_id]
        return matching[-limit:]


class FakeSummaryDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[UUID] = []

    async def dispatch(self, conversation_id: UUID) -> None:
        self.dispatched.append(conversation_id)


class FakeLLMPort:
    def __init__(self, response_text: str = "a summary") -> None:
        self.response_text = response_text
        self.complete_calls: list[str] = []

    async def complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> LLMCompletionResult:
        self.complete_calls.append(prompt)
        return LLMCompletionResult(
            text=self.response_text, prompt_tokens=10, completion_tokens=5, finish_reason="stop"
        )

    def stream_complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        raise NotImplementedError
