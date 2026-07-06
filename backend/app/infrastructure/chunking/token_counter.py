from functools import lru_cache

from tokenizers import Tokenizer

# The actual BGE-M3 tokenizer (not an approximation) — loaded via the
# lightweight `tokenizers` package rather than the full `transformers`
# stack, since only tokenization (not model inference) is needed here.
# `Tokenizer.from_pretrained` fetches `tokenizer.json` from the Hub on
# first use and caches it locally, so every chunker and Module 9's
# embedding adapter share one source of truth for token accounting.
_TOKENIZER_ID = "BAAI/bge-m3"


@lru_cache(maxsize=1)
def _get_tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(_TOKENIZER_ID)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_get_tokenizer().encode(text).ids)
