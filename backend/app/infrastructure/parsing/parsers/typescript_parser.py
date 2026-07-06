from typing import ClassVar

import tree_sitter
import tree_sitter_typescript as tstypescript

from app.infrastructure.parsing.base_parser import BaseTreeSitterParser
from app.infrastructure.parsing.models import ImportInfo, ParsedFile, SymbolInfo
from app.infrastructure.parsing.parsers._ecmascript_common import (
    parse_import_statement,
    walk_for_symbols,
)
from app.infrastructure.parsing.registry import register_parser

# The TSX grammar is a strict superset of plain TypeScript (verified: it
# parses ordinary .ts source with zero errors), so one grammar covers
# both extensions without needing to sniff which one we were handed —
# `parse()` only receives bytes, never a filename.
_LANGUAGE = tree_sitter.Language(tstypescript.language_tsx())


@register_parser
class TypeScriptParser(BaseTreeSitterParser):
    language_id: ClassVar[str] = "typescript"
    file_extensions: ClassVar[frozenset[str]] = frozenset({".ts", ".tsx"})
    _language: ClassVar[tree_sitter.Language] = _LANGUAGE

    def extract_symbols(self, parsed: ParsedFile) -> list[SymbolInfo]:
        return walk_for_symbols(parsed.tree.root_node)

    def extract_imports(self, parsed: ParsedFile) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for node in parsed.tree.root_node.children:
            if node.type == "import_statement":
                info = parse_import_statement(node)
                if info is not None:
                    imports.append(info)
        return imports
