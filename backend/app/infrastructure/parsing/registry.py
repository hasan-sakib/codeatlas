from app.infrastructure.parsing.base_parser import LanguageParser


class UnsupportedLanguageError(Exception):
    """No parser is registered for the requested language id."""


class ParserRegistrationError(Exception):
    """A parser tried to claim a language id or file extension already
    claimed by a different parser — almost certainly a bug (e.g. a
    typo'd extension), never something to silently override."""


class ParserRegistry:
    """Plugin registry parsers join via the `@register_parser` decorator
    at import time. Callers (language_detector.py, Module 8's chunker,
    the future indexing pipeline) resolve a parser purely through this
    registry — never via an if/elif chain over language names, so adding
    language N+1 means adding one new parser file plus one import line in
    `parsers/__init__.py`, with zero edits here or to existing parsers.
    """

    _by_language_id: dict[str, type[LanguageParser]] = {}
    _by_extension: dict[str, type[LanguageParser]] = {}

    @classmethod
    def register(cls, parser_cls: type[LanguageParser]) -> type[LanguageParser]:
        language_id = parser_cls.language_id
        if language_id in cls._by_language_id:
            raise ParserRegistrationError(
                f"Language id {language_id!r} is already registered to "
                f"{cls._by_language_id[language_id].__name__}"
            )
        for extension in parser_cls.file_extensions:
            if extension in cls._by_extension:
                raise ParserRegistrationError(
                    f"Extension {extension!r} is already registered to "
                    f"{cls._by_extension[extension].__name__} "
                    f"(conflicts with {parser_cls.__name__})"
                )

        cls._by_language_id[language_id] = parser_cls
        for extension in parser_cls.file_extensions:
            cls._by_extension[extension] = parser_cls
        return parser_cls

    @classmethod
    def get_by_language_id(cls, language_id: str) -> LanguageParser:
        parser_cls = cls._by_language_id.get(language_id)
        if parser_cls is None:
            raise UnsupportedLanguageError(f"No parser registered for language id {language_id!r}")
        return parser_cls()

    @classmethod
    def get_by_extension(cls, extension: str) -> LanguageParser | None:
        parser_cls = cls._by_extension.get(extension)
        return parser_cls() if parser_cls is not None else None

    @classmethod
    def supported_languages(cls) -> frozenset[str]:
        return frozenset(cls._by_language_id)


def register_parser(parser_cls: type[LanguageParser]) -> type[LanguageParser]:
    return ParserRegistry.register(parser_cls)
