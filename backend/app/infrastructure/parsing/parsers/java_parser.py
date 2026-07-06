from typing import ClassVar

from app.infrastructure.parsing.models import ImportInfo, ParsedFile, SymbolInfo
from app.infrastructure.parsing.registry import register_parser

_NOT_IMPLEMENTED = "Java parsing is not yet implemented — this is a registry extension-point stub"


@register_parser
class JavaParser:
    """See go_parser.py — same extension-point-stub rationale, for
    `.java`."""

    language_id: ClassVar[str] = "java"
    file_extensions: ClassVar[frozenset[str]] = frozenset({".java"})

    def parse(self, source: bytes) -> ParsedFile:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def extract_symbols(self, parsed: ParsedFile) -> list[SymbolInfo]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def extract_imports(self, parsed: ParsedFile) -> list[ImportInfo]:
        raise NotImplementedError(_NOT_IMPLEMENTED)
