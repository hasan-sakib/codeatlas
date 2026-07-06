from app.infrastructure.parsing.parsers.typescript_parser import TypeScriptParser


def test_extract_symbols_arrow_function_and_method() -> None:
    source = b"const foo = (): number => 1;\n\nclass Foo {\n  method(): void {}\n}\n"
    parser = TypeScriptParser()
    parsed = parser.parse(source)

    symbols = parser.extract_symbols(parsed)
    by_name = {s.name: s.kind for s in symbols}

    assert by_name["foo"] == "function"
    assert by_name["Foo"] == "class"
    assert by_name["method"] == "method"


def test_extract_symbols_handles_jsx_without_error() -> None:
    source = b"function Component() {\n  return <div>hello</div>;\n}\n"
    parser = TypeScriptParser()
    parsed = parser.parse(source)

    assert not parsed.tree.root_node.has_error
    symbols = parser.extract_symbols(parsed)
    assert [s.name for s in symbols] == ["Component"]


def test_extract_symbols_handles_exported_function() -> None:
    source = b"export function exported() {}\n"
    parser = TypeScriptParser()
    parsed = parser.parse(source)

    symbols = parser.extract_symbols(parsed)
    assert [s.name for s in symbols] == ["exported"]


def test_extract_symbols_ignores_interface_and_type_alias() -> None:
    source = b"interface Foo {\n  bar(): void;\n}\ntype Baz = string;\n"
    parser = TypeScriptParser()
    parsed = parser.parse(source)

    symbols = parser.extract_symbols(parsed)
    assert symbols == []
