from app.agent.state import AgentState


def error_handler_node(state: AgentState) -> dict[str, object]:
    error = state.get("error") or "an unexpected error occurred"
    message = f"Sorry, I couldn't process that request due to a system error. Details: {error}"
    return {"final_answer": message, "citations": []}
