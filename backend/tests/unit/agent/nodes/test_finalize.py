from uuid import uuid4

from app.agent.nodes.finalize import finalize_node
from app.domain.entities.message import Citation, MessageRole
from tests.unit.agent.fakes import FakeManageConversationUseCase


async def test_finalize_persists_assistant_message_with_citations() -> None:
    conversation_id = uuid4()
    citation = Citation(chunk_id=uuid4(), file_path="a.py", start_line=1, end_line=2, score=0.9)
    use_case = FakeManageConversationUseCase()

    result = await finalize_node(
        {
            "conversation_id": conversation_id,
            "final_answer": "the answer",
            "citations": [citation],
        },
        manage_conversation_use_case=use_case,
    )

    assert result == {}
    assert use_case.appended == [(conversation_id, MessageRole.ASSISTANT, "the answer", [citation])]


async def test_finalize_persists_empty_string_when_no_final_answer() -> None:
    conversation_id = uuid4()
    use_case = FakeManageConversationUseCase()

    await finalize_node({"conversation_id": conversation_id}, manage_conversation_use_case=use_case)

    assert use_case.appended == [(conversation_id, MessageRole.ASSISTANT, "", [])]
