import tree_sitter

from app.infrastructure.chunking._line_window import line_window_split, slice_lines
from app.infrastructure.chunking.models import ChunkCandidate
from app.infrastructure.chunking.token_counter import count_tokens
from app.infrastructure.parsing.models import ParsedFile, SymbolInfo


class AstChunker:
    """Cuts code along function/class/module boundaries using Module 7's
    SymbolInfo ranges. A symbol that fits under budget becomes one chunk;
    an oversized one is split by recursively descending into the
    tree-sitter node's own named children (see `_split_node`), falling
    back to fixed line-window slicing only once no further AST boundary
    exists.
    """

    def __init__(self, max_chunk_tokens: int, min_chunk_tokens: int) -> None:
        self._max_chunk_tokens = max_chunk_tokens
        self._min_chunk_tokens = min_chunk_tokens

    def chunk(
        self, parsed: ParsedFile, symbols: list[SymbolInfo], file_path: str
    ) -> list[ChunkCandidate]:
        lines = parsed.source.decode(errors="replace").splitlines(keepends=True)
        if not lines:
            return []

        top_level = _select_top_level_symbols(sorted(symbols, key=lambda s: s.start_line))

        candidates: list[ChunkCandidate] = []
        cursor = 1
        for symbol in top_level:
            if symbol.start_line > cursor:
                candidates.extend(
                    self._module_gap_candidate(
                        lines, cursor, symbol.start_line - 1, parsed, file_path
                    )
                )

            candidates.extend(self._chunk_symbol(parsed, lines, symbol, file_path))
            cursor = symbol.end_line + 1

        if cursor <= len(lines):
            candidates.extend(
                self._module_gap_candidate(lines, cursor, len(lines), parsed, file_path)
            )

        return candidates

    def _chunk_symbol(
        self, parsed: ParsedFile, lines: list[str], symbol: SymbolInfo, file_path: str
    ) -> list[ChunkCandidate]:
        text = slice_lines(lines, symbol.start_line, symbol.end_line)
        if count_tokens(text) <= self._max_chunk_tokens:
            return [
                self._make_candidate(
                    text,
                    symbol.kind,
                    symbol.name,
                    symbol.start_line,
                    symbol.end_line,
                    parsed,
                    file_path,
                    "ast",
                )
            ]

        node = parsed.tree.root_node.descendant_for_point_range(
            (symbol.start_line - 1, 0), _end_point(lines, symbol.end_line)
        )
        if node is None:
            pieces = line_window_split(
                lines,
                symbol.start_line,
                symbol.end_line,
                self._max_chunk_tokens,
                self._min_chunk_tokens,
            )
        else:
            pieces = _split_node(
                node,
                lines,
                self._max_chunk_tokens,
                self._min_chunk_tokens,
                symbol.start_line,
                symbol.end_line,
            )

        return [
            self._make_candidate(
                p_text, symbol.kind, symbol.name, p_start, p_end, parsed, file_path, "ast"
            )
            for p_start, p_end, p_text in pieces
        ]

    def _module_gap_candidate(
        self, lines: list[str], start_line: int, end_line: int, parsed: ParsedFile, file_path: str
    ) -> list[ChunkCandidate]:
        text = slice_lines(lines, start_line, end_line)
        if not text.strip():
            return []
        if count_tokens(text) <= self._max_chunk_tokens:
            return [
                self._make_candidate(
                    text, "module", None, start_line, end_line, parsed, file_path, "ast"
                )
            ]
        pieces = line_window_split(
            lines, start_line, end_line, self._max_chunk_tokens, self._min_chunk_tokens
        )
        return [
            self._make_candidate(p_text, "module", None, p_start, p_end, parsed, file_path, "ast")
            for p_start, p_end, p_text in pieces
        ]

    def _make_candidate(
        self,
        text: str,
        symbol_kind: str,
        symbol_name: str | None,
        start_line: int,
        end_line: int,
        parsed: ParsedFile,
        file_path: str,
        source_stage: str,
    ) -> ChunkCandidate:
        return ChunkCandidate(
            text=text,
            token_count=count_tokens(text),
            file_path=file_path,
            language=parsed.language_id,
            symbol_kind=symbol_kind,  # type: ignore[arg-type]
            symbol_name=symbol_name,
            start_line=start_line,
            end_line=end_line,
            source_stage=source_stage,  # type: ignore[arg-type]
        )


def _select_top_level_symbols(symbols: list[SymbolInfo]) -> list[SymbolInfo]:
    """A symbol nested inside a preceding selected symbol's line range
    (e.g. a method inside its class) is already covered by that symbol's
    own chunk once the outer symbol fits under budget — so it's dropped
    here rather than double-chunked. If the outer symbol turns out to be
    oversized, `_split_node`'s generic tree descent rediscovers the same
    boundaries independently (a class's only named children are its name
    and body block; the body block's named children are its methods), so
    nothing is lost by excluding nested symbols upfront.
    """
    top_level: list[SymbolInfo] = []
    for symbol in symbols:
        if top_level:
            outer = top_level[-1]
            if outer.start_line <= symbol.start_line and symbol.end_line <= outer.end_line:
                continue
        top_level.append(symbol)
    return top_level


def _end_point(lines: list[str], line: int) -> tuple[int, int]:
    if line < 1 or line > len(lines):
        return (max(line - 1, 0), 0)
    return (line - 1, len(lines[line - 1].rstrip("\n").rstrip("\r")))


def _split_node(
    node: tree_sitter.Node,
    lines: list[str],
    max_tokens: int,
    min_tokens: int,
    start_line: int,
    end_line: int,
) -> list[tuple[int, int, str]]:
    text = slice_lines(lines, start_line, end_line)
    if count_tokens(text) <= max_tokens:
        return [(start_line, end_line, text)]

    children = list(node.named_children)
    if not children:
        return line_window_split(lines, start_line, end_line, max_tokens, min_tokens)

    # Partition [start_line, end_line] into one "unit" per child. Each
    # unit starts right where the previous one ended (absorbing any
    # inter-child gap — punctuation, comments, blank lines — into the
    # unit that follows), the first unit starts at `start_line`, and the
    # last ends at `end_line` — guaranteeing full, gap-free,
    # non-overlapping coverage regardless of what sits between children.
    units: list[tuple[tree_sitter.Node, int, int]] = []
    cursor = start_line
    for i, child in enumerate(children):
        unit_end = end_line if i == len(children) - 1 else children[i + 1].start_point.row
        units.append((child, cursor, unit_end))
        cursor = unit_end + 1

    # Greedily merge consecutive units while the combined text stays
    # under budget.
    merged: list[tuple[int, int, list[tree_sitter.Node]]] = []
    for child, u_start, u_end in units:
        if merged:
            m_start, _m_end, m_children = merged[-1]
            candidate_text = slice_lines(lines, m_start, u_end)
            if count_tokens(candidate_text) <= max_tokens:
                merged[-1] = (m_start, u_end, m_children + [child])
                continue
        merged.append((u_start, u_end, [child]))

    pieces: list[tuple[int, int, str]] = []
    for m_start, m_end, m_children in merged:
        piece_text = slice_lines(lines, m_start, m_end)
        if count_tokens(piece_text) <= max_tokens:
            pieces.append((m_start, m_end, piece_text))
        elif len(m_children) == 1:
            # Still oversized on its own — descend into this child's own
            # named children (the "next-best AST boundary").
            pieces.extend(_split_node(m_children[0], lines, max_tokens, min_tokens, m_start, m_end))
        else:
            # Defensive fallback: shouldn't occur (a multi-child group
            # that's over budget would have failed to merge above), but
            # guard against it rather than risk an infinite loop.
            pieces.extend(line_window_split(lines, m_start, m_end, max_tokens, min_tokens))

    return pieces
