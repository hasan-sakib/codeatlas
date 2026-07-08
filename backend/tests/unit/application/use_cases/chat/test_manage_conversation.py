from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.use_cases.chat.manage_conversation import ManageConversationUseCase
from app.domain.entities.conversation import Conversation
from app.domain.entities.message import Citation, MessageRole
from app.domain.exceptions import ConversationNotFoundError
from app.infrastructure.llm.token_utils import count_tokens
from tests.unit.application.use_cases.chat.fakes import (
    FakeConversationRepository,
    FakeMessageRepository,
    FakeSummaryDispatcher,
)


def _conversation(**overrides: object) -> Conversation:
    now = datetime.now(UTC)
    defaults: dict[str, object] = dict(
        id=uuid4(),
        workspace_id=uuid4(),
        user_id=uuid4(),
        title=None,
        summary=None,
        turn_count=0,
        is_deleted=False,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Conversation(**defaults)  # type: ignore[arg-type]


async def test_create_conversation_persists_with_zero_turn_count() -> None:
    conversation_repo = FakeConversationRepository()
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )
    workspace_id, user_id = uuid4(), uuid4()

    conversation = await use_case.create_conversation(workspace_id, user_id, title="hi")

    assert conversation.workspace_id == workspace_id
    assert conversation.user_id == user_id
    assert conversation.title == "hi"
    assert conversation.turn_count == 0
    assert conversation.is_deleted is False
    assert conversation_repo.conversations[conversation.id] == conversation


async def test_append_message_persists_message_with_real_token_count() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    message_repo = FakeMessageRepository()
    use_case = ManageConversationUseCase(conversation_repo, message_repo, FakeSummaryDispatcher())

    message = await use_case.append_message(
        conversation.id, MessageRole.USER, "what does foo() do?"
    )

    assert message.content == "what does foo() do?"
    assert message.role == MessageRole.USER
    assert message.token_count == count_tokens("what does foo() do?")
    assert message.citations == []
    assert message_repo.messages == [message]


async def test_append_message_stores_citations_when_given() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )
    citation = Citation(chunk_id=uuid4(), file_path="a.py", start_line=1, end_line=2, score=0.5)

    message = await use_case.append_message(
        conversation.id, MessageRole.ASSISTANT, "it does x", citations=[citation]
    )

    assert message.citations == [citation]


async def test_append_message_increments_turn_count() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    await use_case.append_message(conversation.id, MessageRole.USER, "one")
    await use_case.append_message(conversation.id, MessageRole.USER, "two")

    assert conversation_repo.conversations[conversation.id].turn_count == 2


async def test_append_message_dispatches_summarization_exactly_at_threshold() -> None:
    conversation = _conversation(turn_count=8)
    conversation_repo = FakeConversationRepository([conversation])
    dispatcher = FakeSummaryDispatcher()
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), dispatcher, summary_threshold=10
    )

    await use_case.append_message(conversation.id, MessageRole.USER, "turn nine")  # 8 -> 9
    assert dispatcher.dispatched == []

    await use_case.append_message(conversation.id, MessageRole.USER, "turn ten")  # 9 -> 10
    assert dispatcher.dispatched == [conversation.id]

    await use_case.append_message(conversation.id, MessageRole.USER, "turn eleven")  # 10 -> 11
    assert dispatcher.dispatched == [conversation.id]  # not dispatched again


async def test_append_message_propagates_conversation_not_found() -> None:
    use_case = ManageConversationUseCase(
        FakeConversationRepository(), FakeMessageRepository(), FakeSummaryDispatcher()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.append_message(uuid4(), MessageRole.USER, "hi")


async def test_get_context_window_returns_summary_and_recent_messages() -> None:
    conversation = _conversation(summary="prior summary")
    conversation_repo = FakeConversationRepository([conversation])
    message_repo = FakeMessageRepository()
    use_case = ManageConversationUseCase(conversation_repo, message_repo, FakeSummaryDispatcher())
    await use_case.append_message(conversation.id, MessageRole.USER, "hi")
    await use_case.append_message(conversation.id, MessageRole.ASSISTANT, "hello")

    summary, messages = await use_case.get_context_window(conversation.id, max_turns=10)

    assert summary == "prior summary"
    assert [m.content for m in messages] == ["hi", "hello"]


async def test_get_context_window_raises_for_unknown_conversation() -> None:
    use_case = ManageConversationUseCase(
        FakeConversationRepository(), FakeMessageRepository(), FakeSummaryDispatcher()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.get_context_window(uuid4(), max_turns=10)


async def test_get_context_window_raises_for_soft_deleted_conversation() -> None:
    conversation = _conversation(is_deleted=True)
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.get_context_window(conversation.id, max_turns=10)


async def test_list_conversations_filters_by_user_and_workspace_excluding_deleted() -> None:
    user_id, workspace_id = uuid4(), uuid4()
    mine = _conversation(user_id=user_id, workspace_id=workspace_id)
    someone_elses = _conversation(user_id=uuid4(), workspace_id=workspace_id)
    deleted = _conversation(user_id=user_id, workspace_id=workspace_id, is_deleted=True)
    other_workspace = _conversation(user_id=user_id, workspace_id=uuid4())
    conversation_repo = FakeConversationRepository([mine, someone_elses, deleted, other_workspace])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    results = await use_case.list_conversations(user_id, workspace_id)

    assert [c.id for c in results] == [mine.id]


async def test_get_conversation_returns_it_when_in_the_right_workspace() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    result = await use_case.get_conversation(conversation.id, conversation.workspace_id)

    assert result == conversation


async def test_get_conversation_raises_for_wrong_workspace() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.get_conversation(conversation.id, uuid4())


async def test_delete_conversation_soft_deletes() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    await use_case.delete_conversation(conversation.id, conversation.workspace_id)

    assert conversation_repo.conversations[conversation.id].is_deleted is True


async def test_delete_conversation_raises_for_wrong_workspace_without_deleting() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.delete_conversation(conversation.id, uuid4())

    assert conversation_repo.conversations[conversation.id].is_deleted is False


async def test_list_messages_returns_recent_messages_for_the_conversation() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    message_repo = FakeMessageRepository()
    use_case = ManageConversationUseCase(conversation_repo, message_repo, FakeSummaryDispatcher())
    await use_case.append_message(conversation.id, MessageRole.USER, "hi")
    await use_case.append_message(conversation.id, MessageRole.ASSISTANT, "hello")

    messages = await use_case.list_messages(conversation.id, conversation.workspace_id)

    assert [m.content for m in messages] == ["hi", "hello"]


async def test_list_messages_raises_for_wrong_workspace() -> None:
    conversation = _conversation()
    conversation_repo = FakeConversationRepository([conversation])
    use_case = ManageConversationUseCase(
        conversation_repo, FakeMessageRepository(), FakeSummaryDispatcher()
    )

    with pytest.raises(ConversationNotFoundError):
        await use_case.list_messages(conversation.id, uuid4())
