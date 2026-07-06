from dataclasses import dataclass
from typing import Literal

import tree_sitter

from app.domain.value_objects.clone_result import BlameEntry


@dataclass(frozen=True)
class ParsedFile:
    """The tree-sitter `Tree` never leaks past this package — Module 8's
    chunker consumes `SymbolInfo`/`ImportInfo` only, so the tree-sitter
    dependency stays fully contained in `infrastructure/parsing`.
    """

    language_id: str
    tree: tree_sitter.Tree
    source: bytes


@dataclass(frozen=True)
class SymbolInfo:
    """A top-level chunk boundary: a module-level function/class, or a
    method directly inside a class body. Deliberately excludes nested
    defs (a function/method defined inside another function) — those
    aren't separate chunk boundaries at this level; Module 8's chunker
    re-consults the tree directly if it needs to split an oversized
    symbol at a nested boundary.

    "module" is part of the taxonomy (shared with Module 8's
    `symbol_kind` payload field) but is never emitted by a parser here —
    the chunker synthesizes a module-kind chunk for code not covered by
    any extracted symbol (imports, top-level constants, docstrings).
    """

    name: str
    kind: Literal["function", "class", "method", "module"]
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ImportInfo:
    module: str
    imported_names: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class ChunkMetadataCandidate:
    symbol: SymbolInfo
    imports: tuple[ImportInfo, ...]
    blame: tuple[BlameEntry, ...]
