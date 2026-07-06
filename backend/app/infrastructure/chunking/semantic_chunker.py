import re
from dataclasses import dataclass

from app.infrastructure.chunking._line_window import line_window_split, slice_lines
from app.infrastructure.chunking.models import ChunkCandidate
from app.infrastructure.chunking.token_counter import count_tokens

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class _Section:
    level: int  # 0 = preamble before any heading
    heading_text: str | None
    start_line: int
    end_line: int


class SemanticChunker:
    """Chunks markdown by heading boundaries first, then a coherence pass
    (merge empty headings forward, split still-oversized sections at
    paragraph boundaries). Docstrings can be handed to `chunk()` too, by
    wrapping the docstring text as a single virtual markdown "file" —
    the caller is responsible for relabeling the resulting
    `symbol_kind="markdown_section"` candidates to `"docstring"` if that
    distinction matters to it, since this method has no way to tell the
    two apart from the text alone.
    """

    def __init__(self, max_chunk_tokens: int, min_chunk_tokens: int) -> None:
        self._max_chunk_tokens = max_chunk_tokens
        self._min_chunk_tokens = min_chunk_tokens

    def chunk(self, markdown_text: str, file_path: str) -> list[ChunkCandidate]:
        lines = markdown_text.splitlines(keepends=True)
        if not lines:
            return []

        sections = _merge_empty_headings(_scan_sections(lines), lines)

        candidates: list[ChunkCandidate] = []
        for section in sections:
            text = slice_lines(lines, section.start_line, section.end_line)
            if not text.strip():
                continue
            if count_tokens(text) <= self._max_chunk_tokens:
                candidates.append(self._make_candidate(text, section, file_path))
                continue

            pieces = _split_by_paragraph(
                lines,
                section.start_line,
                section.end_line,
                self._max_chunk_tokens,
                self._min_chunk_tokens,
            )
            for p_start, p_end, p_text in pieces:
                candidates.append(
                    self._make_candidate(
                        p_text, section, file_path, start_line=p_start, end_line=p_end
                    )
                )

        return candidates

    def _make_candidate(
        self,
        text: str,
        section: _Section,
        file_path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ChunkCandidate:
        return ChunkCandidate(
            text=text,
            token_count=count_tokens(text),
            file_path=file_path,
            language="markdown",
            symbol_kind="markdown_section",
            symbol_name=section.heading_text,
            start_line=start_line if start_line is not None else section.start_line,
            end_line=end_line if end_line is not None else section.end_line,
            source_stage="semantic",
        )


def _scan_sections(lines: list[str]) -> list[_Section]:
    """Every heading (any level) starts a new flat section — this is
    already "the next-lower heading level" split the design calls for:
    if a `##` section contains a `###` subheading before further body
    text, that subheading becomes its own section immediately, rather
    than nested content inside the `##` section.
    """
    raw: list[_Section] = []
    current_level = 0
    current_heading: str | None = None
    current_start = 1

    for i, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line.rstrip("\n").rstrip("\r"))
        if match:
            raw.append(_Section(current_level, current_heading, current_start, i - 1))
            current_level = len(match.group(1))
            current_heading = match.group(2)
            current_start = i

    raw.append(_Section(current_level, current_heading, current_start, len(lines)))
    return [s for s in raw if s.start_line <= s.end_line]


def _merge_empty_headings(sections: list[_Section], lines: list[str]) -> list[_Section]:
    """A heading with no body content of its own (immediately followed by
    another heading, or only blank lines before one) reads oddly as a
    standalone chunk — merge it forward into the section that follows.
    """
    result = list(sections)
    changed = True
    while changed:
        changed = False
        for i, section in enumerate(result):
            if section.level > 0 and not _has_body(section, lines) and i + 1 < len(result):
                nxt = result[i + 1]
                result[i : i + 2] = [
                    _Section(section.level, section.heading_text, section.start_line, nxt.end_line)
                ]
                changed = True
                break
    return result


def _has_body(section: _Section, lines: list[str]) -> bool:
    if section.level == 0:
        return True  # preamble always counts, even if just whitespace
    body_lines = lines[section.start_line : section.end_line]  # heading line itself excluded
    return any(line.strip() for line in body_lines)


def _split_by_paragraph(
    lines: list[str], start_line: int, end_line: int, max_tokens: int, min_tokens: int
) -> list[tuple[int, int, str]]:
    units = _paragraph_units(lines, start_line, end_line)

    merged: list[tuple[int, int]] = []
    for u_start, u_end in units:
        if merged:
            m_start, _m_end = merged[-1]
            candidate = slice_lines(lines, m_start, u_end)
            if count_tokens(candidate) <= max_tokens:
                merged[-1] = (m_start, u_end)
                continue
        merged.append((u_start, u_end))

    pieces: list[tuple[int, int, str]] = []
    for m_start, m_end in merged:
        text = slice_lines(lines, m_start, m_end)
        if count_tokens(text) <= max_tokens:
            pieces.append((m_start, m_end, text))
        else:
            # A single paragraph that alone exceeds budget — no finer
            # boundary is available, fall back to raw line-window slicing.
            pieces.extend(line_window_split(lines, m_start, m_end, max_tokens, min_tokens))
    return pieces


def _paragraph_units(lines: list[str], start_line: int, end_line: int) -> list[tuple[int, int]]:
    """Same contiguous-unit shape as ast_chunker's node splitting: each
    unit runs from just after the previous unit to just before the next
    paragraph's start, absorbing blank-line gaps — first unit starts at
    `start_line`, last ends at `end_line`."""
    para_starts: list[int] = []
    in_para = False
    for line_no in range(start_line, end_line + 1):
        stripped = lines[line_no - 1].strip()
        if stripped and not in_para:
            para_starts.append(line_no)
            in_para = True
        elif not stripped:
            in_para = False

    if not para_starts:
        return [(start_line, end_line)]

    units: list[tuple[int, int]] = []
    for i, p_start in enumerate(para_starts):
        unit_start = start_line if i == 0 else p_start
        unit_end = end_line if i == len(para_starts) - 1 else para_starts[i + 1] - 1
        units.append((unit_start, unit_end))
    return units
