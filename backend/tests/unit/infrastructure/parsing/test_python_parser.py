from pathlib import Path

from app.infrastructure.parsing.models import ImportInfo
from app.infrastructure.parsing.parsers.python_parser import PythonParser

FIXTURE = b"""import os
from typing import Protocol


class Foo:
    def bar(self):
        pass

    def baz(self):
        pass


def top():
    def nested():
        pass
    return nested
"""


def test_extract_symbols_excludes_nested_function() -> None:
    parser = PythonParser()
    parsed = parser.parse(FIXTURE)

    symbols = parser.extract_symbols(parsed)

    assert len(symbols) == 4
    by_name = {s.name: s.kind for s in symbols}
    assert by_name == {"Foo": "class", "bar": "method", "baz": "method", "top": "function"}


def test_extract_imports_distinguishes_plain_and_from_import() -> None:
    parser = PythonParser()
    parsed = parser.parse(FIXTURE)

    imports = parser.extract_imports(parsed)

    assert imports[0].module == "os"
    assert imports[0].imported_names == ()
    assert imports[1].module == "typing"
    assert imports[1].imported_names == ("Protocol",)


def test_extract_imports_handles_aliases_and_relative_imports() -> None:
    source = (
        b"import os.path as op\n"
        b"from . import utils\n"
        b"from .sub import thing as t\n"
        b"from pkg import a, b\n"
    )
    parser = PythonParser()
    parsed = parser.parse(source)

    imports = parser.extract_imports(parsed)

    assert imports[0] == ImportInfo(module="os.path", imported_names=(), line=1)
    assert imports[1].module == "."
    assert imports[1].imported_names == ("utils",)
    assert imports[2].module == ".sub"
    assert imports[2].imported_names == ("t",)
    assert imports[3].module == "pkg"
    assert imports[3].imported_names == ("a", "b")


def test_extract_symbols_handles_decorated_definitions() -> None:
    source = b"@staticmethod\ndef decorated():\n    pass\n"
    parser = PythonParser()
    parsed = parser.parse(source)

    symbols = parser.extract_symbols(parsed)

    assert len(symbols) == 1
    assert symbols[0].name == "decorated"
    assert symbols[0].kind == "function"


def test_parse_does_not_crash_on_malformed_source() -> None:
    parser = PythonParser()
    parsed = parser.parse(b"def broken(:\n    pass\n")

    assert parsed.tree.root_node.has_error
    parser.extract_symbols(parsed)  # must not raise


def test_extract_symbols_on_real_world_file_produces_plausible_count() -> None:
    real_file = (
        Path(__file__).resolve().parents[4]
        / "app"
        / "infrastructure"
        / "vcs"
        / "git_python_adapter.py"
    )
    source = real_file.read_bytes()
    parser = PythonParser()
    parsed = parser.parse(source)

    assert not parsed.tree.root_node.has_error
    symbols = parser.extract_symbols(parsed)
    kinds = [s.kind for s in symbols]

    # Regression pin against the real file as it stands today (1 class,
    # its 6 methods including __init__, 1 module-level helper function) —
    # not a business requirement, just a sanity check that a real,
    # moderately-sized file parses plausibly.
    assert kinds.count("class") == 1
    assert kinds.count("method") == 6
    assert kinds.count("function") == 1
