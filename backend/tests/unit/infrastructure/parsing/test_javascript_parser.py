from app.infrastructure.parsing.parsers.javascript_parser import JavaScriptParser


def test_extract_symbols_handles_arrow_function_and_class_methods() -> None:
    source = (
        b"const arrowFn = () => { return 1; };\n\n"
        b"function plainFn() {}\n\n"
        b"class Foo {\n"
        b"  bar() {}\n"
        b"  async baz() {}\n"
        b"}\n"
    )
    parser = JavaScriptParser()
    parsed = parser.parse(source)

    symbols = parser.extract_symbols(parsed)
    by_name = {s.name: s.kind for s in symbols}

    assert by_name == {
        "arrowFn": "function",
        "plainFn": "function",
        "Foo": "class",
        "bar": "method",
        "baz": "method",
    }


def test_extract_symbols_excludes_nested_function_declaration() -> None:
    source = b"function outer() {\n  function inner() {}\n  return inner;\n}\n"
    parser = JavaScriptParser()
    parsed = parser.parse(source)

    symbols = parser.extract_symbols(parsed)

    assert [s.name for s in symbols] == ["outer"]


def test_extract_imports_named_default_and_namespace() -> None:
    source = (
        b'import { readFile as rf, writeFile } from "fs";\n'
        b'import Default from "./default";\n'
        b'import * as path from "path";\n'
    )
    parser = JavaScriptParser()
    parsed = parser.parse(source)

    imports = parser.extract_imports(parsed)

    assert imports[0].module == "fs"
    assert imports[0].imported_names == ("rf", "writeFile")
    assert imports[1].module == "./default"
    assert imports[1].imported_names == ("Default",)
    assert imports[2].module == "path"
    assert imports[2].imported_names == ("path",)
