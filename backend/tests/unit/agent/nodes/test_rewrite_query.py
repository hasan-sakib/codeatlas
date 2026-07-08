from uuid import uuid4

from app.agent.nodes.rewrite_query import rewrite_query_node
from app.core.config import AgentSettings
from app.domain.entities.message import Message, MessageRole
from app.domain.exceptions import LLMUnavailableError
from app.infrastructure.llm.prompt_renderer import PromptRenderer
from tests.unit.agent.fakes import FakeLLMPort


def _message(role: MessageRole, content: str) -> Message:
    return Message(
        id=uuid4(), conversation_id=uuid4(), role=role, content=content, citations=[], token_count=1
    )


async def test_rewrite_query_skips_llm_when_no_history() -> None:
    llm = FakeLLMPort(complete_text="should never be used")
    result = await rewrite_query_node(
        {"query": "what does foo do?", "messages": []},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result == {"rewritten_query": "what does foo do?"}
    assert llm.complete_calls == []


async def test_rewrite_query_calls_llm_when_history_present() -> None:
    llm = FakeLLMPort(complete_text="what does the parse_file function do?")
    history = [_message(MessageRole.USER, "tell me about parse_file")]
    result = await rewrite_query_node(
        {"query": "what does it do?", "messages": history},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result == {"rewritten_query": "what does the parse_file function do?"}
    assert len(llm.complete_calls) == 1
    assert "tell me about parse_file" in llm.complete_calls[0]


async def test_rewrite_query_falls_back_to_original_on_empty_llm_response() -> None:
    llm = FakeLLMPort(complete_text="   ")
    history = [_message(MessageRole.USER, "hi")]
    result = await rewrite_query_node(
        {"query": "original query", "messages": history},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result == {"rewritten_query": "original query"}


async def test_rewrite_query_sets_error_on_llm_unavailable() -> None:
    llm = FakeLLMPort(raise_on_complete=LLMUnavailableError("down"))
    history = [_message(MessageRole.USER, "hi")]
    result = await rewrite_query_node(
        {"query": "q", "messages": history},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result == {"error": "down"}
