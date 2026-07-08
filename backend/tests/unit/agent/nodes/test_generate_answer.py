from app.agent.nodes.generate_answer import generate_answer_node
from app.agent.state import Intent
from app.core.config import AgentSettings
from app.domain.exceptions import LLMUnavailableError
from app.infrastructure.llm.prompt_renderer import PromptRenderer
from tests.unit.agent.fakes import FakeLLMPort, make_chunk


async def test_generate_answer_uses_general_chat_template_and_skips_chunks() -> None:
    llm = FakeLLMPort(stream_tokens=["hi", " there"])
    result = await generate_answer_node(
        {
            "intent": Intent.GENERAL_CHAT,
            "query": "hey!",
            "messages": [],
            "reranked_chunks": [make_chunk()],
        },
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result["final_answer"] == "hi there"
    assert result["context_chunks"] == []
    assert "Retrieved context" not in llm.stream_calls[0]


async def test_generate_answer_uses_rag_template_with_context_chunks() -> None:
    chunk = make_chunk(text="def foo(): return 42")
    llm = FakeLLMPort(stream_tokens=["it returns 42"])
    result = await generate_answer_node(
        {
            "intent": Intent.CODE_QA,
            "query": "what does foo do?",
            "messages": [],
            "reranked_chunks": [chunk],
        },
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(context_chunk_count=8),
    )
    assert result["final_answer"] == "it returns 42"
    assert result["context_chunks"] == [chunk]
    assert "def foo(): return 42" in llm.stream_calls[0]


async def test_generate_answer_includes_successful_tool_outputs() -> None:
    chunk = make_chunk()
    llm = FakeLLMPort(stream_tokens=["answer"])
    tool_calls = [
        {
            "tool_name": "get_git_blame",
            "arguments": {},
            "result": "abc123 Jane 2026-01-01",
            "error": None,
        },
        {"tool_name": "get_file", "arguments": {}, "result": None, "error": "failed"},
    ]
    await generate_answer_node(
        {
            "intent": Intent.DEBUGGING,
            "query": "q",
            "messages": [],
            "reranked_chunks": [chunk],
            "tool_calls": tool_calls,
        },
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    prompt = llm.stream_calls[0]
    assert "abc123 Jane 2026-01-01" in prompt
    assert "failed" not in prompt  # the errored tool call's (None) result is never included


async def test_generate_answer_limits_to_context_chunk_count() -> None:
    chunks = [make_chunk(file_path=f"f{i}.py") for i in range(5)]
    llm = FakeLLMPort(stream_tokens=["answer"])
    result = await generate_answer_node(
        {"intent": Intent.CODE_QA, "query": "q", "messages": [], "reranked_chunks": chunks},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(context_chunk_count=2),
    )
    assert len(result["context_chunks"]) == 2


async def test_generate_answer_falls_back_when_model_produces_no_tokens() -> None:
    llm = FakeLLMPort(stream_tokens=[])
    result = await generate_answer_node(
        {"intent": Intent.CODE_QA, "query": "q", "messages": [], "reranked_chunks": [make_chunk()]},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert "wasn't able to produce an answer" in result["final_answer"]


async def test_generate_answer_sets_error_on_llm_unavailable() -> None:
    llm = FakeLLMPort(raise_on_stream=LLMUnavailableError("down"))
    result = await generate_answer_node(
        {"intent": Intent.CODE_QA, "query": "q", "messages": [], "reranked_chunks": []},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result == {"error": "down"}
