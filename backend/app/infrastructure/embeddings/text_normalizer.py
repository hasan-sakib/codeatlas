import hashlib
import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_cache_key(text: str, model_id: str) -> str:
    """Whitespace-insensitive cache key: `sha256(model_id + ":" + normalized_text)`.

    `model_id` (not just the text) is folded into the hash so it
    doubles as the embedding-version namespace — bumping `model_id` in
    config naturally invalidates every old cache entry with no explicit
    flush, since the new key never collides with the old one.
    """
    normalized = _WHITESPACE_RE.sub(" ", text.strip())
    digest_input = f"{model_id}:{normalized}".encode()
    return hashlib.sha256(digest_input).hexdigest()
