import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.middleware.correlation_id import CORRELATION_ID_HEADER
from app.api.schemas.common import ProblemDetail
from app.core.logging import get_correlation_id
from app.domain.exceptions import (
    ConversationNotFoundError,
    DomainError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LLMUnavailableError,
    RepositoryAlreadyIndexingError,
    RepositoryNotFoundError,
    WorkspaceNotFoundError,
    WorkspaceSlugAlreadyExistsError,
)

logger = structlog.get_logger(__name__)

# Exact-type lookup (not isinstance) — every DomainError subtype must be
# registered here explicitly, so adding a new domain exception without
# also deciding its HTTP status is a visible gap (see the "unmapped"
# fallback below) rather than an accidental isinstance-match on a
# semantically unrelated ancestor.
_STATUS_BY_EXCEPTION_TYPE: dict[type[DomainError], int] = {
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    EmailAlreadyExistsError: status.HTTP_409_CONFLICT,
    InvalidRefreshTokenError: status.HTTP_401_UNAUTHORIZED,
    WorkspaceNotFoundError: status.HTTP_404_NOT_FOUND,
    WorkspaceSlugAlreadyExistsError: status.HTTP_409_CONFLICT,
    RepositoryNotFoundError: status.HTTP_404_NOT_FOUND,
    RepositoryAlreadyIndexingError: status.HTTP_409_CONFLICT,
    LLMUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    ConversationNotFoundError: status.HTTP_404_NOT_FOUND,
}

_DEFAULT_TITLES: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: "Unauthorized",
    status.HTTP_404_NOT_FOUND: "Not Found",
    status.HTTP_409_CONFLICT: "Conflict",
    status.HTTP_503_SERVICE_UNAVAILABLE: "Service Unavailable",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal Server Error",
}


def _problem_response(request: Request, http_status: int, detail: str | None) -> JSONResponse:
    correlation_id = get_correlation_id()
    problem = ProblemDetail(
        type=f"https://codeatlas.dev/errors/{http_status}",
        title=_DEFAULT_TITLES.get(http_status, "Error"),
        status=http_status,
        detail=detail,
        instance=str(request.url.path),
        correlation_id=correlation_id,
    )
    headers = {CORRELATION_ID_HEADER: correlation_id} if correlation_id else None
    return JSONResponse(
        status_code=http_status,
        content=problem.model_dump(),
        media_type="application/problem+json",
        headers=headers,
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    http_status = _STATUS_BY_EXCEPTION_TYPE.get(type(exc))
    if http_status is None:
        # A DomainError subtype was raised without ever being added to
        # the map above — a real gap, not a client error. Logged loudly
        # and surfaced as a 500 rather than silently defaulting to some
        # guessed client-error status.
        logger.error("error_handling.unmapped_domain_error", exception_type=type(exc).__name__)
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    return _problem_response(request, http_status, str(exc) or None)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "error_handling.unhandled_exception",
        exception_type=type(exc).__name__,
        exception_message=str(exc),
    )
    # Never leak internals (stack traces, exception messages that might
    # embed a query string/SQL/file path) into the response body.
    return _problem_response(request, status.HTTP_500_INTERNAL_SERVER_ERROR, None)


def register_exception_handlers(app: FastAPI) -> None:
    # add_exception_handler's stub is typed generically as
    # Callable[[Request, Exception], ...] — a handler narrowed to a
    # specific Exception subclass is exactly what Starlette expects and
    # dispatches correctly at runtime (only ever called with a matching
    # instance), but doesn't structurally satisfy that broader signature.
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
