from dataclasses import dataclass


@dataclass(frozen=True)
class LLMCompletionResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    finish_reason: str
