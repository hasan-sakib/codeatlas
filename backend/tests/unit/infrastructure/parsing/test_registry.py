import pytest

from app.infrastructure.parsing.registry import (
    ParserRegistrationError,
    ParserRegistry,
    UnsupportedLanguageError,
    register_parser,
)


def test_register_parser_populates_both_lookup_maps() -> None:
    class FakeParser:
        language_id = "zz-populate-test"
        file_extensions = frozenset({".zzpopulate"})

        def parse(self, source: bytes) -> None:  # pragma: no cover - unused
            raise NotImplementedError

        def extract_symbols(self, parsed: object) -> list[object]:  # pragma: no cover
            raise NotImplementedError

        def extract_imports(self, parsed: object) -> list[object]:  # pragma: no cover
            raise NotImplementedError

    register_parser(FakeParser)  # type: ignore[arg-type]

    assert "zz-populate-test" in ParserRegistry.supported_languages()
    resolved = ParserRegistry.get_by_extension(".zzpopulate")
    assert resolved is not None
    assert resolved.language_id == "zz-populate-test"
    assert ParserRegistry.get_by_language_id("zz-populate-test").language_id == "zz-populate-test"


def test_register_parser_rejects_duplicate_extension() -> None:
    class FakeParserX:
        language_id = "zz-dup-ext-x"
        file_extensions = frozenset({".zzdupext"})

        def parse(self, source: bytes) -> None: ...
        def extract_symbols(self, parsed: object) -> list[object]: ...
        def extract_imports(self, parsed: object) -> list[object]: ...

    class FakeParserY:
        language_id = "zz-dup-ext-y"
        file_extensions = frozenset({".zzdupext"})

        def parse(self, source: bytes) -> None: ...
        def extract_symbols(self, parsed: object) -> list[object]: ...
        def extract_imports(self, parsed: object) -> list[object]: ...

    register_parser(FakeParserX)  # type: ignore[arg-type]
    with pytest.raises(ParserRegistrationError):
        register_parser(FakeParserY)  # type: ignore[arg-type]


def test_register_parser_rejects_duplicate_language_id() -> None:
    class FakeParserM:
        language_id = "zz-dup-lang"
        file_extensions = frozenset({".zzdupm"})

        def parse(self, source: bytes) -> None: ...
        def extract_symbols(self, parsed: object) -> list[object]: ...
        def extract_imports(self, parsed: object) -> list[object]: ...

    class FakeParserN:
        language_id = "zz-dup-lang"
        file_extensions = frozenset({".zzdupn"})

        def parse(self, source: bytes) -> None: ...
        def extract_symbols(self, parsed: object) -> list[object]: ...
        def extract_imports(self, parsed: object) -> list[object]: ...

    register_parser(FakeParserM)  # type: ignore[arg-type]
    with pytest.raises(ParserRegistrationError):
        register_parser(FakeParserN)  # type: ignore[arg-type]


def test_get_by_language_id_raises_for_unknown_language() -> None:
    with pytest.raises(UnsupportedLanguageError):
        ParserRegistry.get_by_language_id("zz-totally-unknown-language")


def test_get_by_extension_returns_none_for_unknown_extension() -> None:
    assert ParserRegistry.get_by_extension(".zz-totally-unknown-ext") is None
