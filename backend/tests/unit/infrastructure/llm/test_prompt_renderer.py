import pytest
from jinja2 import UndefinedError

from app.infrastructure.llm.prompt_renderer import PromptRenderer


@pytest.fixture
def renderer() -> PromptRenderer:
    return PromptRenderer()


def test_render_rag_answer_with_full_fixture_context(renderer: PromptRenderer) -> None:
    rendered = renderer.render(
        "rag_answer.jinja",
        query="What does foo() do?",
        chunks=[
            {"file_path": "app/foo.py", "start_line": 1, "end_line": 3, "text": "def foo(): pass"}
        ],
        history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        conversation_summary=None,
    )
    assert "What does foo() do?" in rendered
    assert "app/foo.py:1-3" in rendered
    assert "def foo(): pass" in rendered
    assert "user: hi" in rendered
    assert "assistant: hello" in rendered


def test_render_rag_answer_omits_summary_block_when_absent(renderer: PromptRenderer) -> None:
    rendered = renderer.render(
        "rag_answer.jinja", query="q", chunks=[], history=[], conversation_summary=None
    )
    assert "Conversation so far" not in rendered


def test_render_rag_answer_includes_summary_when_present(renderer: PromptRenderer) -> None:
    rendered = renderer.render(
        "rag_answer.jinja",
        query="q",
        chunks=[],
        history=[],
        conversation_summary="user previously asked about auth",
    )
    assert "Conversation so far (summarized): user previously asked about auth" in rendered


def test_render_query_rewrite_with_fixture_context(renderer: PromptRenderer) -> None:
    rendered = renderer.render(
        "query_rewrite.jinja",
        query="what calls that?",
        history=[{"role": "user", "content": "what does parse_file do?"}],
    )
    assert "what calls that?" in rendered
    assert "what does parse_file do?" in rendered


def test_render_summarize_with_fixture_context(renderer: PromptRenderer) -> None:
    rendered = renderer.render(
        "summarize.jinja",
        messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        existing_summary=None,
    )
    assert "user: hi" in rendered
    assert "assistant: hello" in rendered


def test_render_raises_on_missing_required_variable(renderer: PromptRenderer) -> None:
    with pytest.raises(UndefinedError):
        renderer.render("rag_answer.jinja", chunks=[], history=[], conversation_summary=None)
