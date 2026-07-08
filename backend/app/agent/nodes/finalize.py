from app.agent.state import AgentState
from app.application.use_cases.chat.manage_conversation import ManageConversationUseCase
from app.domain.entities.message import MessageRole


async def finalize_node(
    state: AgentState, *, manage_conversation_use_case: ManageConversationUseCase
) -> dict[str, object]:
    # The user's own message is persisted by whichever caller invokes
    # this graph, before invoking it (that caller owns knowing the user
    # actually asked something, independent of how the agent responds).
    # finalize is only responsible for the assistant's turn.
    await manage_conversation_use_case.append_message(
        state["conversation_id"],
        MessageRole.ASSISTANT,
        state.get("final_answer") or "",
        citations=state.get("citations", []),
    )
    return {}
