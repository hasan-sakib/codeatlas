from app.infrastructure.chunking.semantic_chunker import SemanticChunker


def test_empty_section_merges_forward_into_next_sibling() -> None:
    md = "# Title\n\nIntro paragraph.\n\n## Empty\n\n### Real\n\nActual content.\n"

    candidates = SemanticChunker(max_chunk_tokens=512, min_chunk_tokens=1).chunk(md, "README.md")

    names = [c.symbol_name for c in candidates]
    assert names == ["Title", "Empty"]
    merged = next(c for c in candidates if c.symbol_name == "Empty")
    assert "Actual content." in merged.text


def test_oversized_section_splits_at_paragraph_boundaries() -> None:
    paragraphs = [
        f"Paragraph {i} with some reasonably long filler content for token counting."
        for i in range(6)
    ]
    md = "# Big\n\n" + "\n\n".join(paragraphs) + "\n"

    candidates = SemanticChunker(max_chunk_tokens=30, min_chunk_tokens=2).chunk(md, "doc.md")

    assert len(candidates) > 1
    assert all(c.token_count <= 30 for c in candidates)
    prev_end = 0
    for candidate in candidates:
        assert candidate.start_line == prev_end + 1
        prev_end = candidate.end_line
    assert prev_end == len(md.splitlines())


def test_normal_sections_become_separate_candidates() -> None:
    md = "# One\n\nBody one.\n\n# Two\n\nBody two.\n"

    candidates = SemanticChunker(max_chunk_tokens=512, min_chunk_tokens=1).chunk(md, "doc.md")

    assert [c.symbol_name for c in candidates] == ["One", "Two"]
    assert all(c.symbol_kind == "markdown_section" for c in candidates)
    assert all(c.language == "markdown" for c in candidates)
    assert all(c.source_stage == "semantic" for c in candidates)


def test_empty_markdown_returns_no_candidates() -> None:
    assert SemanticChunker(max_chunk_tokens=512, min_chunk_tokens=1).chunk("", "doc.md") == []
