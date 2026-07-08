from uuid import uuid4

from app.agent.graph import build_agent_graph
from app.core.config import AgentSettings
from app.domain.exceptions import LLMUnavailableError
from app.domain.value_objects.llm_completion_result import LLMCompletionResult
from app.infrastructure.llm.prompt_renderer import PromptRenderer
from tests.unit.agent.fakes import (
    FakeManageConversationUseCase,
    FakeRerankerPort,
    FakeRetrievalService,
    FakeTool,
    make_chunk,
)


class ScriptedLLM:
    """Deterministic per-call-type responses, no real network — codifies
    the behavior already verified by hand against a live Ollama instance
    (see docs/modules/langgraph_agent.md) as a permanent regression test
    that runs in the fast, model-free checked-in suite."""

    def __init__(self, intent: str = "code_qa", answer_tokens: list[str] | None = None) -> None:
        self.intent = intent
        self.answer_tokens = answer_tokens if answer_tokens is not None else ["the", " answer"]

    async def complete(self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2):
        if "Category:" in prompt:
            return LLMCompletionResult(
                text=self.intent, prompt_tokens=1, completion_tokens=1, finish_reason="stop"
            )
        return LLMCompletionResult(
            text="rewritten query", prompt_tokens=1, completion_tokens=1, finish_reason="stop"
        )

    async def stream_complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ):
        for token in self.answer_tokens:
            yield token


def _build_graph(
    llm, retrieval_service=None, reranker=None, manage_conversation=None, settings=None
):
    return build_agent_graph(
        llm_port=llm,
        retrieval_service=retrieval_service or FakeRetrievalService(),
        reranker_port=reranker or FakeRerankerPort(),
        manage_conversation_use_case=manage_conversation or FakeManageConversationUseCase(),
        prompt_renderer=PromptRenderer(),
        get_file_tool=FakeTool(),
        get_git_blame_tool=FakeTool(result="abc1234 Jane 2026-01-01"),
        run_search_tool=FakeTool(),
        settings=settings or AgentSettings(),
    )


def _initial_state(query: str) -> dict:
    return {
        "conversation_id": uuid4(),
        "workspace_id": uuid4(),
        "user_id": uuid4(),
        "query": query,
        "embedding_version": "bge-m3:v1",
        "conversation_summary": None,
        "messages": [],
        "retrieval_attempts": 0,
        "tool_calls": [],
    }


async def test_code_qa_happy_path_produces_grounded_answer_and_citations() -> None:
    chunk = make_chunk(file_path="app/foo.py")
    manage_conversation = FakeManageConversationUseCase()
    graph = _build_graph(
        ScriptedLLM(intent="code_qa"),
        retrieval_service=FakeRetrievalService(results=[chunk]),
        manage_conversation=manage_conversation,
    )

    final = await graph.ainvoke(_initial_state("what does foo do?"))

    assert final["intent"].value == "code_qa"
    assert final["final_answer"] == "the answer"
    assert final["citations"][0].chunk_id == chunk.chunk_id
    assert final.get("error") is None
    assert len(manage_conversation.appended) == 1


async def test_general_chat_skips_retrieval_entirely() -> None:
    retrieval = FakeRetrievalService()
    graph = _build_graph(ScriptedLLM(intent="general_chat"), retrieval_service=retrieval)

    final = await graph.ainvoke(_initial_state("thanks for the help!"))

    assert final["intent"].value == "general_chat"
    assert retrieval.calls == []
    assert "retrieved_chunks" not in final
    assert final["final_answer"] == "the answer"


async def test_debugging_intent_triggers_exactly_one_git_blame_call() -> None:
    chunk = make_chunk()
    blame_tool = FakeTool(result="abc1234 Jane 2026-01-01")
    graph = build_agent_graph(
        llm_port=ScriptedLLM(intent="debugging"),
        retrieval_service=FakeRetrievalService(results=[chunk]),
        reranker_port=FakeRerankerPort(),
        manage_conversation_use_case=FakeManageConversationUseCase(),
        prompt_renderer=PromptRenderer(),
        get_file_tool=FakeTool(),
        get_git_blame_tool=blame_tool,
        run_search_tool=FakeTool(),
        settings=AgentSettings(),
    )

    final = await graph.ainvoke(_initial_state("I'm seeing a ValueError, why?"))

    assert len(blame_tool.calls) == 1
    assert len(final["tool_calls"]) == 1
    assert final["tool_calls"][0]["tool_name"] == "get_git_blame"


async def test_retrieval_retries_with_widened_k_then_succeeds() -> None:
    chunk = make_chunk()
    retrieval = FakeRetrievalService(results=[])  # first call empty
    call_count = {"n": 0}

    async def flaky(query):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return []
        return [chunk]

    retrieval.retrieve_without_rerank = flaky  # type: ignore[method-assign]

    graph = _build_graph(
        ScriptedLLM(intent="code_qa"),
        retrieval_service=retrieval,
        settings=AgentSettings(max_retrieval_attempts=2),
    )

    final = await graph.ainvoke(_initial_state("what does foo do?"))

    assert final["retrieval_attempts"] == 2
    assert final["citations"][0].chunk_id == chunk.chunk_id


async def test_retrieval_exhausts_retries_and_still_answers() -> None:
    retrieval = FakeRetrievalService(results=[])  # always empty
    graph = _build_graph(
        ScriptedLLM(intent="code_qa"),
        retrieval_service=retrieval,
        settings=AgentSettings(max_retrieval_attempts=2),
    )

    final = await graph.ainvoke(_initial_state("what does foo do?"))

    assert final["retrieval_attempts"] == 2
    assert final["final_answer"] == "the answer"
    assert final["citations"] == []


class AlwaysFailingLLM:
    async def complete(self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2):
        raise LLMUnavailableError("simulated outage")

    async def stream_complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ):
        raise LLMUnavailableError("simulated outage")
        yield  # pragma: no cover - makes this an async generator


async def test_llm_failure_routes_to_error_handler_and_still_finalizes() -> None:
    manage_conversation = FakeManageConversationUseCase()
    graph = _build_graph(AlwaysFailingLLM(), manage_conversation=manage_conversation)

    final = await graph.ainvoke(_initial_state("what does foo do?"))

    assert final["error"] == "simulated outage"
    assert "simulated outage" in final["final_answer"]
    assert len(manage_conversation.appended) == 1  # error answer is still persisted


async def test_astream_custom_mode_emits_token_events_during_generate_answer() -> None:
    graph = _build_graph(ScriptedLLM(intent="code_qa", answer_tokens=["a", "b", "c"]))

    custom_events = []
    async for mode, payload in graph.astream(_initial_state("q"), stream_mode=["custom", "values"]):
        if mode == "custom":
            custom_events.append(payload)

    assert custom_events == [
        {"type": "token", "text": "a"},
        {"type": "token", "text": "b"},
        {"type": "token", "text": "c"},
    ]
