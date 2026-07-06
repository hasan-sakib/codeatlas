from typing import ClassVar

import tree_sitter
import tree_sitter_python as tspython

from app.infrastructure.parsing.base_parser import BaseTreeSitterParser
from app.infrastructure.parsing.models import ImportInfo, ParsedFile, SymbolInfo
from app.infrastructure.parsing.registry import register_parser

_LANGUAGE = tree_sitter.Language(tspython.language())


def _text(node: tree_sitter.Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode()


@register_parser
class PythonParser(BaseTreeSitterParser):
    language_id: ClassVar[str] = "python"
    file_extensions: ClassVar[frozenset[str]] = frozenset({".py"})
    _language: ClassVar[tree_sitter.Language] = _LANGUAGE

    def extract_symbols(self, parsed: ParsedFile) -> list[SymbolInfo]:
        return _walk_for_symbols(parsed.tree.root_node, in_class=False)

    def extract_imports(self, parsed: ParsedFile) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for node in parsed.tree.root_node.children:
            if node.type == "import_statement":
                imports.extend(_parse_import_statement(node))
            elif node.type == "import_from_statement":
                imports.append(_parse_import_from_statement(node))
        return imports


def _walk_for_symbols(node: tree_sitter.Node, *, in_class: bool) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []
    for child in node.children:
        if child.type == "class_definition":
            symbols.append(_symbol_from_node(child, kind="class"))
            body = child.child_by_field_name("body")
            if body is not None:
                symbols.extend(_walk_for_symbols(body, in_class=True))
        elif child.type == "function_definition":
            symbols.append(_symbol_from_node(child, kind="method" if in_class else "function"))
            # Deliberately don't recurse into a def's own body — nested
            # defs aren't separate top-level chunk boundaries; Module 8's
            # chunker re-consults the tree directly if it needs to split
            # an oversized function at a nested boundary.
        else:
            # Handles decorated_definition (decorators), if-blocks, etc. —
            # anything that isn't itself a def/class but might contain one.
            symbols.extend(_walk_for_symbols(child, in_class=in_class))
    return symbols


def _symbol_from_node(node: tree_sitter.Node, *, kind: str) -> SymbolInfo:
    name = _text(node.child_by_field_name("name")) or "<anonymous>"
    return SymbolInfo(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
    )


def _parse_import_statement(node: tree_sitter.Node) -> list[ImportInfo]:
    line = node.start_point.row + 1
    imports: list[ImportInfo] = []
    for child in node.named_children:
        if child.type == "dotted_name":
            imports.append(ImportInfo(module=_text(child), imported_names=(), line=line))
        elif child.type == "aliased_import":
            module_node = child.named_children[0] if child.named_children else None
            imports.append(ImportInfo(module=_text(module_node), imported_names=(), line=line))
    return imports


def _parse_import_from_statement(node: tree_sitter.Node) -> ImportInfo:
    line = node.start_point.row + 1
    module_node: tree_sitter.Node | None = None
    imported_names: list[str] = []
    seen_import_keyword = False

    for child in node.children:
        if child.type == "import":
            seen_import_keyword = True
            continue
        if not seen_import_keyword:
            if child.type in ("dotted_name", "relative_import"):
                module_node = child
            continue
        if child.type == "dotted_name":
            imported_names.append(_text(child))
        elif child.type == "aliased_import":
            # Record the local alias (what actually appears as a
            # reference name in this file), not the original name.
            alias_node = child.named_children[-1] if child.named_children else None
            imported_names.append(_text(alias_node))
        elif child.type == "wildcard_import":
            imported_names.append("*")

    module = _text(module_node) if module_node is not None else "."
    return ImportInfo(module=module, imported_names=tuple(imported_names), line=line)
