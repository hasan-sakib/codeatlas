from collections.abc import AsyncIterator
from typing import Protocol

from app.domain.value_objects.llm_completion_result import LLMCompletionResult


class LLMPort(Protocol):
    async def complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> LLMCompletionResult:
        """Raises LLMUnavailableError if the backend cannot be reached, if
        a transient error (connection/timeout/5xx) persists after
        exhausting the retry budget, or immediately on a non-retryable
        error (e.g. a 4xx) without spending the retry budget on a request
        that will never succeed."""
        ...

    def stream_complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        """Yields incremental text chunks. Raises LLMUnavailableError under
        the same conditions as complete() while establishing the stream;
        a failure after streaming has begun is raised directly (never
        retried, to avoid replaying/duplicating already-yielded output)."""
        ...
