from functools import lru_cache
from typing import Literal

from tokenizers import Tokenizer

# The actual Qwen3 tokenizer (not an approximation), loaded the same way
# Module 8/9 load BGE-M3's — via the lightweight `tokenizers` package
# rather than the full `transformers` stack. Verified directly against a
# real Ollama /api/generate call: this tokenizer's token ids for a given
# string are an exact substring of the ids Ollama's own `context` field
# reports for a prompt containing that string — the only difference is
# the chat-template control tokens (<|im_start|>, etc.) this tokenizer
# doesn't add, which callers must budget for separately (see
# OllamaAdapter's PROMPT_TEMPLATE_OVERHEAD_TOKENS).
_TOKENIZER_ID = "Qwen/Qwen3-4B"


@lru_cache(maxsize=1)
def _get_tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(_TOKENIZER_ID)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_get_tokenizer().encode(text).ids)


def truncate_to_budget(
    segments: list[str], max_tokens: int, *, keep: Literal["newest", "highest_relevance"] = "newest"
) -> list[str]:
    """Drops whole segments (never truncates mid-segment) until the total
    token count fits within max_tokens.

    `segments` is assumed pre-ordered by the caller:
    - keep="newest": oldest-first order (e.g. conversation turns) — drops
      from the front, keeping the most recent segments.
    - keep="highest_relevance": most-relevant-first order (e.g. reranked
      chunks) — drops from the back, keeping the most relevant segments.
    """
    ordered = list(reversed(segments)) if keep == "newest" else list(segments)

    kept: list[str] = []
    total = 0
    for segment in ordered:
        tokens = count_tokens(segment)
        if total + tokens > max_tokens:
            break
        kept.append(segment)
        total += tokens

    return list(reversed(kept)) if keep == "newest" else kept
