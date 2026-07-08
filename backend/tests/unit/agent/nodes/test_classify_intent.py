import pytest

from app.agent.nodes.classify_intent import classify_intent_edge, classify_intent_node
from app.agent.state import Intent
from app.core.config import AgentSettings
from app.domain.exceptions import LLMUnavailableError
from app.infrastructure.llm.prompt_renderer import PromptRenderer
from tests.unit.agent.fakes import FakeLLMPort


async def test_classify_intent_exact_match() -> None:
    llm = FakeLLMPort(complete_text="debugging")
    result = await classify_intent_node(
        {"query": "why does this crash?"},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result["intent"] == Intent.DEBUGGING


async def test_classify_intent_tolerates_extra_words_around_the_label() -> None:
    llm = FakeLLMPort(complete_text="Category: code_qa.")
    result = await classify_intent_node(
        {"query": "what does foo do?"},
        llm_port=llm,
        prompt_renderer=PromptRenderer(),
        settings=AgentSettings(),
    )
    assert result["intent"] == Intent.CODE_QA


async def test_classify_intent_defaults_to_code_qa_when_unparseable() -> None:
    llm = FakeLLMPort(complete_text="uh, not sure, maybe something else entirely")
    result = await classify_intent_node(
        {"query": "hmm"}, llm_port=llm, prompt_renderer=PromptRenderer(), settings=AgentSettings()
    )
    assert result["intent"] == Intent.CODE_QA


async def test_classify_intent_sets_error_on_llm_unavailable() -> None:
    llm = FakeLLMPort(raise_on_complete=LLMUnavailableError("down"))
    result = await classify_intent_node(
        {"query": "hi"}, llm_port=llm, prompt_renderer=PromptRenderer(), settings=AgentSettings()
    )
    assert result == {"error": "down"}


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"error": "boom"}, "error_handler"),
        ({"intent": Intent.GENERAL_CHAT}, "generate_answer"),
        ({"intent": Intent.CODE_QA}, "rewrite_query"),
        ({}, "rewrite_query"),
    ],
)
def test_classify_intent_edge_routes_correctly(state: dict, expected: str) -> None:
    assert classify_intent_edge(state) == expected  # type: ignore[arg-type]
