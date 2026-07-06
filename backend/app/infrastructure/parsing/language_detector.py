from pathlib import Path

from app.infrastructure.parsing.registry import ParserRegistry

# Interpreter name (as it appears in a shebang line) -> registered
# language id. Only covers interpreters relevant to currently-registered
# languages; extend alongside new parsers.
_SHEBANG_LANGUAGE_HINTS: dict[str, str] = {
    "python": "python",
    "python3": "python",
    "node": "javascript",
}


def detect_language(file_path: Path, content_sample: bytes | None = None) -> str | None:
    """Primary lookup is by extension via the registry; falls back to
    shebang sniffing for extensionless scripts. Returns None if neither
    resolves — callers decide how to handle an undetectable file (skip,
    log, etc.), this function never raises.
    """
    parser = ParserRegistry.get_by_extension(file_path.suffix)
    if parser is not None:
        return parser.language_id

    if content_sample is None:
        return None
    return _detect_from_shebang(content_sample)


def _detect_from_shebang(content_sample: bytes) -> str | None:
    first_line = content_sample.split(b"\n", 1)[0]
    if not first_line.startswith(b"#!"):
        return None

    tokens = first_line[2:].decode(errors="ignore").strip().split()
    if not tokens:
        return None

    # `#!/usr/bin/env python3` -> interpreter is the last token;
    # `#!/usr/bin/python3` -> interpreter is the path itself.
    interpreter_path = tokens[-1] if Path(tokens[0]).name == "env" else tokens[0]
    interpreter_name = Path(interpreter_path).name
    return _SHEBANG_LANGUAGE_HINTS.get(interpreter_name)
