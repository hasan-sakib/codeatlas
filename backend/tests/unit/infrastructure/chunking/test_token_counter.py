from app.infrastructure.chunking.token_counter import count_tokens


def test_count_tokens_empty_string_is_zero() -> None:
    assert count_tokens("") == 0


def test_count_tokens_scales_monotonically_with_length() -> None:
    short = count_tokens("hello")
    longer = count_tokens("hello world, this is a longer sentence with more words")
    assert longer > short


def test_count_tokens_matches_hand_verified_count_for_fixed_string() -> None:
    # Regression pin against tokenizer/version drift — verified by
    # actually running the real BAAI/bge-m3 tokenizer (tokenizers==0.23.1):
    # adds <s>/</s> special tokens plus a SentencePiece split of "BGE-M3"
    # into several subword pieces.
    text = "Hello world, this is a test of the BGE-M3 tokenizer."
    assert count_tokens(text) == 20
