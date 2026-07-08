from app.agent.nodes.tool_router import tool_router_edge, tool_router_node
from app.agent.state import Intent
from app.core.config import AgentSettings
from tests.unit.agent.fakes import make_chunk


def test_tool_router_selects_get_git_blame_for_debugging_with_chunks() -> None:
    result = tool_router_node(
        {"intent": Intent.DEBUGGING, "reranked_chunks": [make_chunk()], "tool_calls": []},
        settings=AgentSettings(),
    )
    assert result == {"next_tool": "get_git_blame"}


def test_tool_router_does_not_repeat_a_tool_already_called() -> None:
    already_called = [{"tool_name": "get_git_blame", "arguments": {}, "result": "x", "error": None}]
    result = tool_router_node(
        {
            "intent": Intent.DEBUGGING,
            "reranked_chunks": [make_chunk()],
            "tool_calls": already_called,
        },
        settings=AgentSettings(),
    )
    assert result == {"next_tool": None}


def test_tool_router_skips_non_debugging_intents() -> None:
    result = tool_router_node(
        {"intent": Intent.CODE_QA, "reranked_chunks": [make_chunk()], "tool_calls": []},
        settings=AgentSettings(),
    )
    assert result == {"next_tool": None}


def test_tool_router_skips_debugging_with_no_chunks() -> None:
    result = tool_router_node(
        {"intent": Intent.DEBUGGING, "reranked_chunks": [], "tool_calls": []},
        settings=AgentSettings(),
    )
    assert result == {"next_tool": None}


def test_tool_router_respects_max_tool_calls_cap() -> None:
    calls = [
        {"tool_name": f"t{i}", "arguments": {}, "result": "x", "error": None} for i in range(3)
    ]
    result = tool_router_node(
        {"intent": Intent.DEBUGGING, "reranked_chunks": [make_chunk()], "tool_calls": calls},
        settings=AgentSettings(max_tool_calls=3),
    )
    assert result == {"next_tool": None}


def test_tool_router_edge_routes_on_next_tool() -> None:
    assert tool_router_edge({"next_tool": "get_git_blame"}) == "call_tool"
    assert tool_router_edge({"next_tool": None}) == "generate_answer"
    assert tool_router_edge({}) == "generate_answer"
