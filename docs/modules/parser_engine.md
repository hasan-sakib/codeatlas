# Module 7: Parser Engine

## Purpose

Turn raw source bytes into language-aware syntax trees plus extracted metadata (symbols, imports, git blame) via tree-sitter, through a plugin registry so a new language never requires touching existing parser code.

## Layering

- `app/infrastructure/parsing/models.py` — `ParsedFile`, `SymbolInfo`, `ImportInfo`, `ChunkMetadataCandidate`. The tree-sitter `Tree` type is wrapped in `ParsedFile` but never leaks further — Module 8's chunker will only ever see `SymbolInfo`/`ImportInfo` dataclasses, so the tree-sitter dependency stays fully contained in this package.
- `app/infrastructure/parsing/registry.py` — `ParserRegistry`, a process-wide singleton populated by the `@register_parser` class decorator at import time. Two lookups: `get_by_language_id` (raises `UnsupportedLanguageError` if unknown — callers with a specific language id expect it to exist) and `get_by_extension` (returns `None` if unknown — used by `language_detector.py`'s "try, then fall back" flow).
- `app/infrastructure/parsing/base_parser.py` — the `LanguageParser` Protocol (`parse`/`extract_symbols`/`extract_imports`) plus `BaseTreeSitterParser`, which handles the shared `Parser(language).parse(source)` boilerplate so each concrete parser only implements the two extraction methods.
- `app/infrastructure/parsing/parsers/` — one file per language. `_ecmascript_common.py` holds symbol/import extraction shared by `javascript_parser.py` and `typescript_parser.py` (both grammars produce identical node shapes for the constructs handled here), so that logic lives once instead of being duplicated. `go_parser.py`/`java_parser.py` are registered-but-stub (`parse()` raises `NotImplementedError`) — they exist purely to prove the registry scales to a new language without touching Python/JS/TS files; no `tree-sitter-go`/`tree-sitter-java` dependency was added for languages we don't parse yet.
- `app/infrastructure/parsing/language_detector.py` — extension lookup via the registry, falling back to shebang sniffing (`#!/usr/bin/env python3` and `#!/usr/bin/python3` forms) for extensionless scripts.
- `app/infrastructure/parsing/metadata_extractor.py` — ties a parsed file's symbols to per-symbol `git blame` calls (Module 6's `GitPort`), producing the `ChunkMetadataCandidate`s Module 8 will consume.

## Decisions verified empirically, not assumed

tree-sitter's Python bindings API has shifted across versions, so every claim below was checked by actually running the installed packages (`tree-sitter==0.23.2`, `tree-sitter-python/-javascript/-typescript==0.23.x`) rather than trusted from training data:

1. **One TypeScript parser handles both `.ts` and `.tsx`.** `LanguageParser.parse()` only receives bytes, never a filename, so the parser can't sniff the extension. Verified that `tree_sitter_typescript.language_tsx()` parses plain (non-JSX) TypeScript with zero errors — the TSX grammar is a strict superset — so `TypeScriptParser` uses it unconditionally for both extensions instead of needing two parser classes or a filename hint threaded through the Protocol.
2. **`extract_symbols()` returns only module-level functions/classes and methods directly inside a class body — nested defs are deliberately excluded.** Confirmed by parsing a fixture with a top-level function, a class with two methods, and a nested function: the walk stops descending once it finds a `function_definition`/`method_definition`, so the nested function never appears. This matches Module 8's own design: its chunker re-consults the tree directly (via the returned line ranges) if it needs to split an oversized symbol at a nested boundary — Module 7 isn't responsible for flattening every lexical scope.
3. **Tree-sitter's error recovery means `parse()` never raises on malformed source.** A syntactically broken file produces a tree containing `ERROR` nodes (`root_node.has_error == True`); `extract_symbols`'s generic recursion just doesn't find real `function_definition`/`class_definition` nodes inside the wreckage and returns fewer (or zero) symbols — verified directly rather than assumed from tree-sitter's general reputation for fault tolerance.
4. **Import parsing needed positional token-flag logic, not just `named_children`.** For `from typing import Protocol, List`, tree-sitter-python's `named_children` returns three indistinguishable `dotted_name` nodes (`typing`, `Protocol`, `List`) with no type-based way to tell "the module" from "the imported names." Fixed by walking raw `children` (including anonymous keyword tokens) and tracking whether the literal `import` keyword token has been seen yet — verified against multiple real import forms (aliased, relative, wildcard) before trusting the logic.

## Testing notes

- Unit tests for the registry use uniquely-named fake parsers per test (`zz-`-prefixed sentinel language ids/extensions) to avoid polluting the shared singleton registry across tests, since real registrations from `parsers/__init__.py` persist for the whole test session.
- `test_python_parser.py` includes a regression test against a real file from this repo (`app/infrastructure/vcs/git_python_adapter.py`) rather than a synthetic multi-hundred-line fixture — parses it and pins the exact symbol counts (1 class, 6 methods, 1 function) as they stand today, catching any future grammar-version upgrade that silently changes node shapes.
- `test_metadata_extractor.py` uses a fake `GitPort` and asserts the exact `(repo_path, file_path, start_line, end_line)` tuple passed to `get_blame` for each symbol, and that the same file-scoped import list is attached to every `ChunkMetadataCandidate` in a file.
- `pytest -q`: 139 passed (27 new). `mypy app`: no issues, 115 source files. `ruff`/`black`: clean. `pre-commit run --all-files`: clean.
- No live-server smoke test for this module — it has no HTTP surface yet (consumed by the future indexing pipeline, not the API directly). Verified instead by running the parsers directly against real Python/JS/TS snippets end-to-end during development, and confirmed the app still boots cleanly with the parser registry populated independently of the FastAPI app lifecycle.

## Known limitations (tracked as follow-ups, not fixed now)

- JS/TS class fields assigned an arrow function (`field = () => {}`, no `const`) aren't extracted — only `const`/`let`/`var`-declared arrow functions are. Not required by the current design's testing plan; add a `field_definition` branch to `_ecmascript_common.walk_for_symbols` if this comes up.
- The Python `_symbols_from_variable_declaration`-equivalent doesn't exist for Python (no `def`-free way to assign a "function" in idiomatic Python), so this only applies to the ECMAScript family — not a gap, just noting the asymmetry is intentional.
- Go/Java parsing raises `NotImplementedError` — tracked for whenever those languages are prioritized; adding real support is "one new file + one import line in `parsers/__init__.py`" per the registry design, with zero edits to this module's existing files.
