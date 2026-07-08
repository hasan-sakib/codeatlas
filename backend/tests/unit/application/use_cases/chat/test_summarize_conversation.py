from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.use_cases.chat.summarize_conversation import SummarizeConversationUseCase
from app.domain.entities.conversation import Conversation
from app.domain.entities.message import Message, MessageRole
from app.domain.exceptions import ConversationNotFoundError
from app.infrastructure.llm.prompt_renderer import PromptRenderer
from tests.unit.application.use_cases.chat.fakes import (
    FakeConversationRepository,
    FakeLLMPort,
    FakeMessageRepository,
)


def _conversation(**overrides: object) -> Conversation:
    now = datetime.now(UTC)
    defaults: dict[str, object] = dict(
        id=uuid4(),
        workspace_id=uuid4(),
        user_id=uuid4(),
        title=None,
        summary=None,
        turn_count=2,
        is_deleted=False,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Conversation(**defaults)  # type: ignore[arg-type]


def _message(conversation_id, role: MessageRole, content: str) -> Message:  # type: ignore[no-untyped-def]
    return Message(
        id=uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations=[],
        token_count=1,
    )


async def test_execute_renders_prompt_calls_llm_and_persists_summary() -> None:
    conversation = _conversation(summary="old summary")
    conversation_repo = FakeConversationRepository([conversation])
    message_repo = FakeMessageRepository()
    message_repo.messages = [
        _message(conversation.id, MessageRole.USER, "what does foo do?"),
        _message(conversation.id, MessageRole.ASSISTANT, "it does x"),
    ]
    llm = FakeLLMPort(response_text="new summary")
    use_case = SummarizeConversationUseCase(
        conversation_repo, message_repo, llm, PromptRenderer(), context_turns=20
    )

    result = await use_case.execute(conversation.id)

    assert result == "new summary"
    assert conversation_repo.update_summary_calls == [(conversation.id, "new summary")]
    assert len(llm.complete_calls) == 1
    prompt = llm.complete_calls[0]
    assert "old summary" in prompt
    assert "what does foo do?" in prompt
    assert "it does x" in prompt


async def test_execute_omits_existing_summary_block_when_none() -> None:
    conversation = _conversation(summary=None)
    conversation_repo = FakeConversationRepository([conversation])
    llm = FakeLLMPort()
    use_case = SummarizeConversationUseCase(
        conversation_repo, FakeMessageRepository(), llm, PromptRenderer()
    )

    await use_case.execute(conversation.id)

    assert "Existing summary" not in llm.complete_calls[0]


async def test_execute_raises_for_unknown_conversation() -> None:
    use_case = SummarizeConversationUseCase(
        FakeConversationRepository(), FakeMessageRepository(), FakeLLMPort(), PromptRenderer()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.execute(uuid4())


async def test_execute_raises_for_soft_deleted_conversation() -> None:
    conversation = _conversation(is_deleted=True)
    conversation_repo = FakeConversationRepository([conversation])
    use_case = SummarizeConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeLLMPort(), PromptRenderer()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.execute(conversation.id)
