from collections.abc import AsyncIterator
from uuid import UUID

from app.domain.value_objects.llm_completion_result import LLMCompletionResult
from app.domain.value_objects.ranked_chunk import RankedChunk


def make_chunk(**overrides: object) -> RankedChunk:
    defaults: dict[str, object] = dict(
        chunk_id=None,
        file_path="app/foo.py",
        start_line=1,
        end_line=5,
        symbol_name="foo",
        score=0.9,
        source="fused",
        text="def foo(): return 42",
    )
    defaults.update(overrides)
    if defaults["chunk_id"] is None:
        from uuid import uuid4

        defaults["chunk_id"] = uuid4()
    return RankedChunk(**defaults)  # type: ignore[arg-type]


class FakeLLMPort:
    """Deterministic, no real network/model — the real model's behavior
    (thinking mode, streaming shape) is verified separately by hand
    against a live Ollama instance (see docs/modules/langgraph_agent.md);
    this fake exists to test the graph's own logic/wiring, not the LLM."""

    def __init__(
        self,
        complete_text: str = "a response",
        stream_tokens: list[str] | None = None,
        raise_on_complete: Exception | None = None,
        raise_on_stream: Exception | None = None,
    ) -> None:
        self.complete_text = complete_text
        self.stream_tokens = stream_tokens if stream_tokens is not None else ["a", " response"]
        self.raise_on_complete = raise_on_complete
        self.raise_on_stream = raise_on_stream
        self.complete_calls: list[str] = []
        self.stream_calls: list[str] = []

    async def complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> LLMCompletionResult:
        self.complete_calls.append(prompt)
        if self.raise_on_complete:
            raise self.raise_on_complete
        return LLMCompletionResult(
            text=self.complete_text, prompt_tokens=1, completion_tokens=1, finish_reason="stop"
        )

    async def stream_complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        self.stream_calls.append(prompt)
        if self.raise_on_stream:
            raise self.raise_on_stream
        for token in self.stream_tokens:
            yield token


class FakeRetrievalService:
    def __init__(
        self, results: list[RankedChunk] | None = None, raise_exc: Exception | None = None
    ) -> None:
        self.results = results if results is not None else [make_chunk()]
        self.raise_exc = raise_exc
        self.calls: list[object] = []

    async def retrieve_without_rerank(self, query: object) -> list[RankedChunk]:
        self.calls.append(query)
        if self.raise_exc:
            raise self.raise_exc
        return self.results

    async def retrieve(self, query: object) -> list[RankedChunk]:
        self.calls.append(query)
        return self.results


class FakeRerankerPort:
    def __init__(self, reordered: list[RankedChunk] | None = None) -> None:
        self.reordered = reordered
        self.calls: list[tuple[str, list[RankedChunk]]] = []

    async def score(self, query: str, chunks: list[RankedChunk]) -> list[RankedChunk]:
        self.calls.append((query, chunks))
        return self.reordered if self.reordered is not None else list(chunks)


class FakeManageConversationUseCase:
    def __init__(self) -> None:
        self.appended: list[tuple[UUID, object, str, object]] = []

    async def append_message(
        self, conversation_id: UUID, role: object, content: str, citations: object = None
    ) -> None:
        self.appended.append((conversation_id, role, content, citations))


class FakeTool:
    def __init__(
        self, result: str = "fake tool result", raise_exc: Exception | None = None
    ) -> None:
        self.result = result
        self.raise_exc = raise_exc
        self.calls: list[tuple[object, ...]] = []

    async def __call__(self, *args: object) -> str:
        self.calls.append(args)
        if self.raise_exc:
            raise self.raise_exc
        return self.result
