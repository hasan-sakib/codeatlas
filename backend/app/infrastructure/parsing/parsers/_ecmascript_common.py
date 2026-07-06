"""Symbol/import extraction shared by JavaScriptParser and
TypeScriptParser — both grammars produce identical node shapes for the
constructs handled here (function/class declarations, methods, `const x
= () => {}`, ES module imports), so this logic lives once instead of
being duplicated across two files.
"""

import tree_sitter

from app.infrastructure.parsing.models import ImportInfo, SymbolInfo

_FUNCTION_VALUE_TYPES = frozenset({"arrow_function", "function_expression"})


def _text(node: tree_sitter.Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode()


def walk_for_symbols(node: tree_sitter.Node, *, in_class: bool = False) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []
    for child in node.children:
        if child.type == "class_declaration":
            symbols.append(_symbol_from_named_node(child, kind="class"))
            body = child.child_by_field_name("body")
            if body is not None:
                symbols.extend(walk_for_symbols(body, in_class=True))
        elif child.type == "method_definition":
            symbols.append(_symbol_from_named_node(child, kind="method"))
            # Deliberately don't recurse into the method's own body —
            # nested defs aren't separate top-level chunk boundaries.
        elif child.type == "function_declaration":
            # Grammar-guaranteed: function_declaration never appears as a
            # class member (classes use method_definition instead), so
            # this is always a plain function regardless of `in_class`.
            symbols.append(_symbol_from_named_node(child, kind="function"))
        elif child.type in ("lexical_declaration", "variable_declaration"):
            symbols.extend(_symbols_from_variable_declaration(child, in_class=in_class))
        else:
            symbols.extend(walk_for_symbols(child, in_class=in_class))
    return symbols


def _symbol_from_named_node(node: tree_sitter.Node, *, kind: str) -> SymbolInfo:
    name = _text(node.child_by_field_name("name")) or "<anonymous>"
    return SymbolInfo(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
    )


def _symbols_from_variable_declaration(
    node: tree_sitter.Node, *, in_class: bool
) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []
    for declarator in node.named_children:
        if declarator.type != "variable_declarator":
            continue
        value = declarator.child_by_field_name("value")
        if value is None or value.type not in _FUNCTION_VALUE_TYPES:
            continue
        name = _text(declarator.child_by_field_name("name")) or "<anonymous>"
        symbols.append(
            SymbolInfo(
                name=name,
                kind="method" if in_class else "function",
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
            )
        )
    return symbols


def parse_import_statement(node: tree_sitter.Node) -> ImportInfo | None:
    source_node = node.child_by_field_name("source")
    if source_node is None:
        return None

    line = node.start_point.row + 1
    module = _string_literal_text(source_node)
    imported_names: list[str] = []
    for child in node.children:
        if child.type != "import_clause":
            continue
        imported_names.extend(_names_from_import_clause(child))
    return ImportInfo(module=module, imported_names=tuple(imported_names), line=line)


def _names_from_import_clause(clause: tree_sitter.Node) -> list[str]:
    names: list[str] = []
    for part in clause.children:
        if part.type == "identifier":
            names.append(_text(part))
        elif part.type == "namespace_import":
            ident = next((c for c in part.children if c.type == "identifier"), None)
            if ident is not None:
                names.append(_text(ident))
        elif part.type == "named_imports":
            for spec in part.named_children:
                if spec.type != "import_specifier":
                    continue
                alias = spec.child_by_field_name("alias")
                chosen = alias if alias is not None else spec.child_by_field_name("name")
                if chosen is not None:
                    names.append(_text(chosen))
    return names


def _string_literal_text(node: tree_sitter.Node) -> str:
    fragment = next((c for c in node.children if c.type == "string_fragment"), None)
    return _text(fragment) if fragment is not None else _text(node)
