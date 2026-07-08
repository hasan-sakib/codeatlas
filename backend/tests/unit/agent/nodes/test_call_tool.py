from uuid import uuid4

from app.agent.nodes.call_tool import call_tool_node
from tests.unit.agent.fakes import FakeTool, make_chunk


async def _call(next_tool, chunks=None, extra=None):
    get_file_tool = FakeTool(result="file contents")
    get_git_blame_tool = FakeTool(result="blame info")
    run_search_tool = FakeTool(result="search results")
    state = {
        "next_tool": next_tool,
        "reranked_chunks": chunks if chunks is not None else [],
        "query": "q",
        "rewritten_query": None,
        "workspace_id": uuid4(),
        "embedding_version": "v1",
    }
    if extra:
        state.update(extra)
    result = await call_tool_node(
        state,
        get_file_tool=get_file_tool,
        get_git_blame_tool=get_git_blame_tool,
        run_search_tool=run_search_tool,
    )
    return result, get_file_tool, get_git_blame_tool, run_search_tool


async def test_call_tool_returns_empty_dict_when_no_next_tool() -> None:
    result, *_ = await _call(None)
    assert result == {}


async def test_call_tool_dispatches_get_file_with_top_chunk() -> None:
    chunk = make_chunk()
    result, get_file_tool, _, _ = await _call("get_file", chunks=[chunk])
    (record,) = result["tool_calls"]
    assert record["tool_name"] == "get_file"
    assert record["result"] == "file contents"
    assert record["error"] is None
    assert get_file_tool.calls == [(chunk.chunk_id,)]
    assert result["next_tool"] is None


async def test_call_tool_dispatches_get_git_blame_with_top_chunk() -> None:
    chunk = make_chunk()
    result, _, get_git_blame_tool, _ = await _call("get_git_blame", chunks=[chunk])
    (record,) = result["tool_calls"]
    assert record["result"] == "blame info"
    assert get_git_blame_tool.calls == [(chunk.chunk_id,)]


async def test_call_tool_dispatches_run_search_with_rewritten_query() -> None:
    result, _, _, run_search_tool = await _call(
        "run_search", extra={"rewritten_query": "better query"}
    )
    (record,) = result["tool_calls"]
    assert record["result"] == "search results"
    assert record["arguments"] == {"query_text": "better query"}
    assert run_search_tool.calls[0][0] == "better query"


async def test_call_tool_records_error_when_no_chunk_available() -> None:
    result, *_ = await _call("get_file", chunks=[])
    (record,) = result["tool_calls"]
    assert record["result"] is None
    assert "No chunk available" in record["error"]


async def test_call_tool_records_error_when_tool_raises() -> None:
    chunk = make_chunk()
    get_file_tool = FakeTool(raise_exc=RuntimeError("boom"))
    result = await call_tool_node(
        {
            "next_tool": "get_file",
            "reranked_chunks": [chunk],
            "query": "q",
            "rewritten_query": None,
            "workspace_id": uuid4(),
            "embedding_version": "v1",
        },
        get_file_tool=get_file_tool,
        get_git_blame_tool=FakeTool(),
        run_search_tool=FakeTool(),
    )
    (record,) = result["tool_calls"]
    assert record["result"] is None
    assert record["error"] == "boom"
