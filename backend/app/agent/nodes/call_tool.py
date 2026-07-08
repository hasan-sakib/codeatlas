from app.agent.state import AgentState, ToolCallRecord
from app.agent.tools.get_file_tool import GetFileTool
from app.agent.tools.get_git_blame_tool import GetGitBlameTool
from app.agent.tools.run_search_tool import RunSearchTool


async def call_tool_node(
    state: AgentState,
    *,
    get_file_tool: GetFileTool,
    get_git_blame_tool: GetGitBlameTool,
    run_search_tool: RunSearchTool,
) -> dict[str, object]:
    tool_name = state.get("next_tool")
    if tool_name is None:
        return {}

    chunks = state.get("reranked_chunks", [])

    try:
        if tool_name == "get_file" and chunks:
            chunk_id = chunks[0].chunk_id
            result = await get_file_tool(chunk_id)
            record = ToolCallRecord(
                tool_name=tool_name,
                arguments={"chunk_id": str(chunk_id)},
                result=result,
                error=None,
            )
        elif tool_name == "get_git_blame" and chunks:
            chunk_id = chunks[0].chunk_id
            result = await get_git_blame_tool(chunk_id)
            record = ToolCallRecord(
                tool_name=tool_name,
                arguments={"chunk_id": str(chunk_id)},
                result=result,
                error=None,
            )
        elif tool_name == "run_search":
            query_text = state.get("rewritten_query") or state["query"]
            result = await run_search_tool(
                query_text, state["workspace_id"], state["embedding_version"]
            )
            record = ToolCallRecord(
                tool_name=tool_name, arguments={"query_text": query_text}, result=result, error=None
            )
        else:
            record = ToolCallRecord(
                tool_name=tool_name,
                arguments={},
                result=None,
                error=f"No chunk available to run {tool_name} against.",
            )
    except Exception as exc:
        # A tool failing is data the LLM can reason about ("blame lookup
        # failed, no clone available"), not a reason to abort the whole
        # turn — matches the design's tool_calls audit-trail intent.
        record = ToolCallRecord(tool_name=tool_name, arguments={}, result=None, error=str(exc))

    return {"tool_calls": [record], "next_tool": None}
