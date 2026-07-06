from app.infrastructure.chunking.ast_chunker import AstChunker
from app.infrastructure.parsing.parsers.python_parser import PythonParser


def test_small_function_becomes_one_candidate_matching_its_range() -> None:
    source = b"def foo():\n    x = 1\n    y = 2\n    return x + y\n"
    parser = PythonParser()
    parsed = parser.parse(source)
    symbols = parser.extract_symbols(parsed)

    candidates = AstChunker(max_chunk_tokens=512, min_chunk_tokens=1).chunk(
        parsed, symbols, "app.py"
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.start_line == 1
    assert candidate.end_line == 4
    assert candidate.symbol_kind == "function"
    assert candidate.symbol_name == "foo"
    assert candidate.source_stage == "ast"


def test_module_level_code_before_first_symbol_becomes_module_chunk() -> None:
    source = b"import os\nCONST = 1\n\n\ndef foo():\n    pass\n"
    parser = PythonParser()
    parsed = parser.parse(source)
    symbols = parser.extract_symbols(parsed)

    candidates = AstChunker(max_chunk_tokens=512, min_chunk_tokens=1).chunk(
        parsed, symbols, "app.py"
    )

    assert candidates[0].symbol_kind == "module"
    assert candidates[0].symbol_name is None
    assert candidates[0].start_line == 1
    # Absorbs the two blank lines before `def foo()` too — the gap
    # candidate spans everything up to (not including) the next symbol.
    assert candidates[0].end_line == 4
    assert candidates[1].symbol_kind == "function"


def test_oversized_function_splits_into_under_budget_pieces_covering_full_range() -> None:
    lines = ["def big():"]
    for i in range(30):
        lines.append(f"    if x == {i}:")
        lines.append(f"        result = compute_something_with_a_fairly_long_name({i})")
        lines.append("        print(result)")
    lines.append("    return result")
    source = ("\n".join(lines) + "\n").encode()

    parser = PythonParser()
    parsed = parser.parse(source)
    symbols = parser.extract_symbols(parsed)

    candidates = AstChunker(max_chunk_tokens=80, min_chunk_tokens=4).chunk(
        parsed, symbols, "app.py"
    )

    assert len(candidates) >= 2
    assert all(c.token_count <= 80 for c in candidates)
    prev_end = 0
    for candidate in candidates:
        assert candidate.start_line == prev_end + 1
        prev_end = candidate.end_line
    assert prev_end == len(lines)


def test_oversized_class_splits_at_method_boundaries_without_duplicating_class_chunk() -> None:
    lines = ["class Big:"]
    for m in range(8):
        lines.append(f"    def method_{m}(self):")
        lines.append(f"        return compute_something_fairly_verbose_for_length({m})")
    source = ("\n".join(lines) + "\n").encode()

    parser = PythonParser()
    parsed = parser.parse(source)
    symbols = parser.extract_symbols(parsed)

    candidates = AstChunker(max_chunk_tokens=40, min_chunk_tokens=4).chunk(
        parsed, symbols, "app.py"
    )

    # Every piece is still tagged as belonging to the class — no separate
    # whole-class chunk plus overlapping per-method chunks.
    assert len(candidates) > 1
    assert all(c.symbol_kind == "class" and c.symbol_name == "Big" for c in candidates)
    assert all(c.token_count <= 40 for c in candidates)
