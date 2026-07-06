from typing import ClassVar

from app.infrastructure.parsing.models import ImportInfo, ParsedFile, SymbolInfo
from app.infrastructure.parsing.registry import register_parser

_NOT_IMPLEMENTED = "Go parsing is not yet implemented — this is a registry extension-point stub"


@register_parser
class GoParser:
    """Extension-point stub: registers `.go` so `ParserRegistry` reports
    it as a known language and `language_detector.py` can resolve it, but
    doesn't parse anything yet. Proves the plugin mechanism scales to a
    new language without touching Python/JS/TS parser files — no
    tree-sitter-go dependency is added until Go support is actually
    implemented (avoids an unused grammar dependency).
    """

    language_id: ClassVar[str] = "go"
    file_extensions: ClassVar[frozenset[str]] = frozenset({".go"})

    def parse(self, source: bytes) -> ParsedFile:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def extract_symbols(self, parsed: ParsedFile) -> list[SymbolInfo]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def extract_imports(self, parsed: ParsedFile) -> list[ImportInfo]:
        raise NotImplementedError(_NOT_IMPLEMENTED)
