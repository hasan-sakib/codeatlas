from functools import lru_cache

from sentence_transformers import CrossEncoder

# Process-wide singleton: CrossEncoderReranker instances are cheap and may
# be constructed fresh per request (see core/di.py's provide_reranker_port),
# but the underlying model must only ever be loaded once per process.
# lru_cache keys on the full (model_name, max_length, device) tuple, which
# in practice is static per process since it comes straight from settings.


@lru_cache(maxsize=1)
def get_cross_encoder(model_name: str, max_length: int, device: str) -> CrossEncoder:
    # CrossEncoder.__init__'s return is loosely typed (Any) despite always
    # constructing a CrossEncoder at this call site.
    model: CrossEncoder = CrossEncoder(model_name, max_length=max_length, device=device)
    return model


def clear_cross_encoder_cache() -> None:
    """Test-only helper, mirrors the other provider cache-clear helpers."""
    get_cross_encoder.cache_clear()
