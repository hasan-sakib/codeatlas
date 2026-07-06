from typing import ClassVar, Protocol

import tree_sitter

from app.infrastructure.parsing.models import ImportInfo, ParsedFile, SymbolInfo


class LanguageParser(Protocol):
    language_id: ClassVar[str]
    file_extensions: ClassVar[frozenset[str]]

    def parse(self, source: bytes) -> ParsedFile: ...
    def extract_symbols(self, parsed: ParsedFile) -> list[SymbolInfo]: ...
    def extract_imports(self, parsed: ParsedFile) -> list[ImportInfo]: ...


class BaseTreeSitterParser:
    """Shared `parse()` boilerplate for tree-sitter-backed parsers.

    Concrete subclasses set `language_id`, `file_extensions`, and
    `_language` (a `tree_sitter.Language` built once at module import
    time from the grammar package) as class attributes, then implement
    only `extract_symbols`/`extract_imports`.
    """

    language_id: ClassVar[str]
    file_extensions: ClassVar[frozenset[str]]
    _language: ClassVar[tree_sitter.Language]

    def parse(self, source: bytes) -> ParsedFile:
        parser = tree_sitter.Parser(self._language)
        tree = parser.parse(source)
        return ParsedFile(language_id=self.language_id, tree=tree, source=source)
