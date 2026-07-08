from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware.error_handling import register_exception_handlers
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


def _app_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (InvalidCredentialsError(), 401),
        (EmailAlreadyExistsError("a@b.com"), 409),
        (InvalidRefreshTokenError(), 401),
        (WorkspaceNotFoundError(), 404),
        (WorkspaceSlugAlreadyExistsError(uuid4(), "my-slug"), 409),
        (RepositoryNotFoundError(), 404),
        (RepositoryAlreadyIndexingError(), 409),
        (LLMUnavailableError("down"), 503),
        (ConversationNotFoundError(uuid4()), 404),
    ],
)
def test_domain_error_maps_to_correct_status(exc: DomainError, expected_status: int) -> None:
    client = _app_raising(exc)
    response = client.get("/boom")
    assert response.status_code == expected_status


def test_domain_error_response_body_is_a_problem_detail() -> None:
    client = _app_raising(WorkspaceNotFoundError("no such workspace"))
    response = client.get("/boom")
    body = response.json()
    assert body["status"] == 404
    assert body["title"]
    assert body["type"]
    assert body["detail"] == "no such workspace"
    assert body["instance"] == "/boom"


def test_unhandled_exception_maps_to_500_without_leaking_details() -> None:
    client = _app_raising(RuntimeError("some internal secret detail"))
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] is None
    assert "some internal secret detail" not in response.text


def test_unmapped_domain_error_falls_back_to_500() -> None:
    class _NewDomainError(DomainError):
        pass

    client = _app_raising(_NewDomainError("oops"))
    response = client.get("/boom")
    assert response.status_code == 500
