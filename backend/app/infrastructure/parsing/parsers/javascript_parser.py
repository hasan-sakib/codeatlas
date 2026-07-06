from typing import ClassVar

import tree_sitter
import tree_sitter_javascript as tsjavascript

from app.infrastructure.parsing.base_parser import BaseTreeSitterParser
from app.infrastructure.parsing.models import ImportInfo, ParsedFile, SymbolInfo
from app.infrastructure.parsing.parsers._ecmascript_common import (
    parse_import_statement,
    walk_for_symbols,
)
from app.infrastructure.parsing.registry import register_parser

_LANGUAGE = tree_sitter.Language(tsjavascript.language())


@register_parser
class JavaScriptParser(BaseTreeSitterParser):
    language_id: ClassVar[str] = "javascript"
    file_extensions: ClassVar[frozenset[str]] = frozenset({".js", ".jsx"})
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
