from uuid import uuid4

from app.application.use_cases.docs.generate_documentation import (
    DocGenerationScope,
    GenerateDocumentationUseCase,
)
from app.domain.value_objects.llm_completion_result import LLMCompletionResult
from app.domain.value_objects.ranked_chunk import RankedChunk
from app.infrastructure.llm.prompt_renderer import PromptRenderer


class FakeRetrievalService:
    def __init__(self, chunks: list[RankedChunk]) -> None:
        self.chunks = chunks
        self.last_query: object = None

    async def retrieve(self, query: object) -> list[RankedChunk]:
        self.last_query = query
        return self.chunks


class FakeLLMPort:
    def __init__(self, text: str = "generated docs") -> None:
        self.text = text
        self.complete_calls: list[str] = []

    async def complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> LLMCompletionResult:
        self.complete_calls.append(prompt)
        return LLMCompletionResult(
            text=self.text, prompt_tokens=1, completion_tokens=1, finish_reason="stop"
        )

    def stream_complete(self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2):
        raise NotImplementedError


def _chunk(**overrides: object) -> RankedChunk:
    defaults: dict[str, object] = dict(
        chunk_id=uuid4(),
        file_path="app/foo.py",
        start_line=1,
        end_line=5,
        symbol_name="foo",
        score=0.9,
        source="fused",
        text="def foo(): return 42",
    )
    defaults.update(overrides)
    return RankedChunk(**defaults)  # type: ignore[arg-type]


async def test_execute_scopes_retrieval_by_repository_and_file_path() -> None:
    retrieval = FakeRetrievalService([_chunk()])
    llm = FakeLLMPort()
    use_case = GenerateDocumentationUseCase(retrieval, llm, PromptRenderer(), "bge-m3:v1")
    workspace_id, repository_id = uuid4(), uuid4()

    await use_case.execute(workspace_id, repository_id, DocGenerationScope.FILE, "app/foo.py")

    query = retrieval.last_query
    assert query.workspace_id == workspace_id  # type: ignore[attr-defined]
    assert query.repository_id == repository_id  # type: ignore[attr-defined]
    assert query.filters.path_prefix == "app/foo.py"  # type: ignore[attr-defined]


async def test_execute_repository_scope_has_no_path_prefix() -> None:
    retrieval = FakeRetrievalService([_chunk()])
    llm = FakeLLMPort()
    use_case = GenerateDocumentationUseCase(retrieval, llm, PromptRenderer(), "bge-m3:v1")

    await use_case.execute(uuid4(), uuid4(), DocGenerationScope.REPOSITORY, None)

    assert retrieval.last_query.filters.path_prefix is None  # type: ignore[attr-defined]


async def test_execute_renders_chunk_content_and_returns_llm_text() -> None:
    chunk = _chunk(file_path="app/bar.py", text="class Bar: pass")
    retrieval = FakeRetrievalService([chunk])
    llm = FakeLLMPort(text="# Bar\n\nA simple class.")
    use_case = GenerateDocumentationUseCase(retrieval, llm, PromptRenderer(), "bge-m3:v1")

    result = await use_case.execute(uuid4(), uuid4(), DocGenerationScope.FILE, "app/bar.py")

    assert result == "# Bar\n\nA simple class."
    assert len(llm.complete_calls) == 1
    prompt = llm.complete_calls[0]
    assert "app/bar.py" in prompt
    assert "class Bar: pass" in prompt


async def test_execute_with_no_matching_chunks_still_calls_llm() -> None:
    retrieval = FakeRetrievalService([])
    llm = FakeLLMPort(text="No information found.")
    use_case = GenerateDocumentationUseCase(retrieval, llm, PromptRenderer(), "bge-m3:v1")

    result = await use_case.execute(uuid4(), uuid4(), DocGenerationScope.MODULE, "app/")

    assert result == "No information found."
    assert len(llm.complete_calls) == 1
