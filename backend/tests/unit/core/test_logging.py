import asyncio
import json
import logging

import pytest
import structlog

from app.core.config import Settings
from app.core.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
    get_correlation_id,
    redact_sensitive_fields,
)


def test_redact_sensitive_fields_masks_known_keys() -> None:
    event_dict = {
        "event": "user.login",
        "password": "hunter2",
        "access_token": "abc123",
        "nested": {"refresh_token": "xyz789", "safe": "keep-me"},
        "safe_field": "keep-me-too",
    }

    result = redact_sensitive_fields(None, "info", event_dict)  # type: ignore[arg-type]

    assert result["password"] == "***REDACTED***"
    assert result["access_token"] == "***REDACTED***"
    assert result["nested"]["refresh_token"] == "***REDACTED***"
    assert result["nested"]["safe"] == "keep-me"
    assert result["safe_field"] == "keep-me-too"
    assert result["event"] == "user.login"


def test_bind_correlation_id_generates_uuid_when_absent() -> None:
    clear_correlation_id()

    cid = bind_correlation_id()

    assert get_correlation_id() == cid
    assert len(cid) == 36  # UUID4 string form

    clear_correlation_id()
    assert get_correlation_id() is None


def test_bind_correlation_id_uses_provided_value() -> None:
    clear_correlation_id()

    cid = bind_correlation_id("client-supplied-id")

    assert cid == "client-supplied-id"
    assert get_correlation_id() == "client-supplied-id"

    clear_correlation_id()


def test_concurrent_tasks_do_not_leak_correlation_id() -> None:
    clear_correlation_id()
    results: dict[str, str | None] = {}

    async def _bind_and_check(name: str, value: str) -> None:
        bind_correlation_id(value)
        await asyncio.sleep(0.01)
        results[name] = get_correlation_id()

    async def _run() -> None:
        await asyncio.gather(
            _bind_and_check("a", "id-a"),
            _bind_and_check("b", "id-b"),
        )

    asyncio.run(_run())

    assert results == {"a": "id-a", "b": "id-b"}


def _make_settings(environment: str) -> Settings:
    return Settings(
        environment=environment,  # type: ignore[arg-type]
        database={"url": "postgresql+asyncpg://u:p@h:5432/d"},  # type: ignore[arg-type]
        qdrant={"url": "http://localhost:6333"},  # type: ignore[arg-type]
        redis={"url": "redis://localhost:6379/0"},  # type: ignore[arg-type]
        ollama={"base_url": "http://localhost:11434"},  # type: ignore[arg-type]
        security={"jwt_secret_key": "test-secret"},  # type: ignore[arg-type]
    )


def test_configure_logging_renders_json_in_production(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(_make_settings("production"))

    structlog.get_logger("test.prod").info("hello", password="should-be-hidden")

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert payload["event"] == "hello"
    assert payload["password"] == "***REDACTED***"
    assert "level" in payload
    assert "timestamp" in payload


def test_configure_logging_renders_console_in_local(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(_make_settings("local"))

    structlog.get_logger("test.local").info("hello-console")

    captured = capsys.readouterr()

    assert "hello-console" in captured.out
    # Console renderer output isn't JSON.
    try:
        json.loads(captured.out.strip())
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("expected non-JSON console output in local environment")


def test_configure_logging_bridges_stdlib_logging(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(_make_settings("production"))

    logging.getLogger("uvicorn.access").info("stdlib log line")

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert payload["event"] == "stdlib log line"
