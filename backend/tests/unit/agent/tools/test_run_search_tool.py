from uuid import uuid4

from app.agent.tools.run_search_tool import RunSearchTool
from tests.unit.agent.fakes import FakeRetrievalService, make_chunk


async def test_run_search_tool_formats_results() -> None:
    service = FakeRetrievalService(results=[make_chunk(file_path="app/foo.py", score=0.876)])
    tool = RunSearchTool(service)

    result = await tool("search text", uuid4(), "bge-m3:v1")

    assert "app/foo.py:1-5" in result
    assert "0.876" in result


async def test_run_search_tool_handles_no_results() -> None:
    service = FakeRetrievalService(results=[])
    tool = RunSearchTool(service)

    result = await tool("nothing matches", uuid4(), "bge-m3:v1")

    assert "No results found" in result
