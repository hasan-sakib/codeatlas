from pathlib import Path

import app.infrastructure.parsing.parsers  # noqa: F401  registers real parsers
from app.infrastructure.parsing.language_detector import detect_language


def test_detect_language_by_extension_python() -> None:
    assert detect_language(Path("foo.py")) == "python"


def test_detect_language_by_extension_typescript_tsx() -> None:
    assert detect_language(Path("component.tsx")) == "typescript"


def test_detect_language_unknown_extension_returns_none() -> None:
    assert detect_language(Path("foo.xyz")) is None


def test_detect_language_shebang_env_python3() -> None:
    content = b"#!/usr/bin/env python3\nprint('hi')\n"
    assert detect_language(Path("script"), content) == "python"


def test_detect_language_shebang_direct_interpreter_path() -> None:
    content = b"#!/usr/bin/python3\nprint('hi')\n"
    assert detect_language(Path("script"), content) == "python"


def test_detect_language_no_shebang_and_no_extension_returns_none() -> None:
    assert detect_language(Path("script"), b"just some text\n") is None


def test_detect_language_unknown_shebang_interpreter_returns_none() -> None:
    content = b"#!/bin/bash\necho hi\n"
    assert detect_language(Path("script"), content) is None
