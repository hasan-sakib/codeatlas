"""Line-slicing and last-resort fixed-window splitting shared by
ast_chunker.py and semantic_chunker.py. Both chunkers reach this only
after every language/heading-aware boundary has been exhausted, so it's
free to make arbitrary line cuts.
"""

from app.infrastructure.chunking.token_counter import count_tokens


def slice_lines(lines: list[str], start_line: int, end_line: int) -> str:
    """1-indexed, inclusive on both ends — matching SymbolInfo/ChunkCandidate
    line-range conventions throughout the codebase."""
    return "".join(lines[start_line - 1 : end_line])


def line_window_split(
    lines: list[str], start_line: int, end_line: int, max_tokens: int, min_tokens: int
) -> list[tuple[int, int, str]]:
    pieces: list[tuple[int, int, str]] = []
    buffer_start = start_line
    buffer_lines: list[str] = []

    for line_no in range(start_line, end_line + 1):
        line = lines[line_no - 1]
        candidate_lines = buffer_lines + [line]
        if buffer_lines and count_tokens("".join(candidate_lines)) > max_tokens:
            pieces.append((buffer_start, line_no - 1, "".join(buffer_lines)))
            buffer_start = line_no
            buffer_lines = [line]
        else:
            buffer_lines = candidate_lines

    if buffer_lines:
        pieces.append((buffer_start, end_line, "".join(buffer_lines)))

    # This path makes arbitrary cuts (no syntactic boundary to respect),
    # so avoid leaving a near-empty trailing sliver by folding it into
    # the previous piece rather than emitting a fragment below min_tokens.
    if len(pieces) >= 2:
        last_start, last_end, last_text = pieces[-1]
        if count_tokens(last_text) < min_tokens:
            prev_start, _prev_end, prev_text = pieces[-2]
            pieces[-2] = (prev_start, last_end, prev_text + last_text)
            pieces.pop()

    return pieces
