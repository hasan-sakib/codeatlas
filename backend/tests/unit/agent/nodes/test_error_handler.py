from app.agent.nodes.error_handler import error_handler_node


def test_error_handler_includes_error_detail_in_final_answer() -> None:
    result = error_handler_node({"error": "Ollama unavailable"})
    assert "Ollama unavailable" in result["final_answer"]
    assert result["citations"] == []


def test_error_handler_has_a_default_message_when_error_is_missing() -> None:
    result = error_handler_node({})
    assert "unexpected error" in result["final_answer"]
