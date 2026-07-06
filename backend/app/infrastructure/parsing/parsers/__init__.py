"""Importing this package triggers every concrete parser's
`@register_parser` decorator, populating `ParserRegistry`. This is the
single import site callers depend on for that side effect —
`import app.infrastructure.parsing.parsers  # noqa: F401`.
"""

from app.infrastructure.parsing.parsers import (  # noqa: F401
    go_parser,
    java_parser,
    javascript_parser,
    python_parser,
    typescript_parser,
)
