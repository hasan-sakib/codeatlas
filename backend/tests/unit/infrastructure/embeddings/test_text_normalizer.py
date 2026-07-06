from app.infrastructure.embeddings.text_normalizer import normalize_for_cache_key


def test_whitespace_collapse_produces_identical_hash() -> None:
    assert normalize_for_cache_key("foo  bar", "model:v1") == normalize_for_cache_key(
        "foo bar", "model:v1"
    )


def test_different_model_ids_produce_different_hashes() -> None:
    assert normalize_for_cache_key("foo bar", "model:v1") != normalize_for_cache_key(
        "foo bar", "model:v2"
    )


def test_leading_trailing_whitespace_is_stripped() -> None:
    assert normalize_for_cache_key("  foo bar  ", "model:v1") == normalize_for_cache_key(
        "foo bar", "model:v1"
    )


def test_returns_a_sha256_hex_digest() -> None:
    result = normalize_for_cache_key("anything", "model:v1")
    assert len(result) == 64
    int(result, 16)  # raises ValueError if not valid hex
