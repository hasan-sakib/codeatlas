import json

import httpx
import pytest
from prometheus_client import REGISTRY

from app.domain.exceptions import LLMUnavailableError
from app.infrastructure.llm import ollama_adapter as oa
from app.infrastructure.llm.ollama_adapter import OllamaAdapter


def _tokens_total(direction: str) -> float:
    return REGISTRY.get_sample_value("llm_tokens_total", {"direction": direction}) or 0.0


def _mock_client_factory(handler: object) -> type:
    class _MockedAsyncClient(httpx.AsyncClient):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]

    return _MockedAsyncClient


def _ndjson(*objs: dict[str, object]) -> bytes:
    return "\n".join(json.dumps(o) for o in objs).encode() + b"\n"


def _adapter(**overrides: object) -> OllamaAdapter:
    defaults: dict[str, object] = {
        "base_url": "http://fake-ollama:11434",
        "model": "qwen3:4b",
        "max_retries": 3,
        "backoff_base_seconds": 0.001,  # keep retry tests fast
    }
    defaults.update(overrides)
    return OllamaAdapter(**defaults)  # type: ignore[arg-type]


async def test_complete_success_parses_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": "Hello there",
                "prompt_eval_count": 12,
                "eval_count": 34,
                "done_reason": "stop",
            },
        )

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))
    result = await _adapter().complete("say hi")

    assert result.text == "Hello there"
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 34
    assert result.finish_reason == "stop"


async def test_complete_sends_max_tokens_and_temperature_as_ollama_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"response": "ok"})

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))
    await _adapter(num_ctx=4096).complete("hi", max_tokens=777, temperature=0.9)

    body = captured["body"]
    assert body["options"]["num_predict"] == 777
    assert body["options"]["temperature"] == 0.9
    assert body["options"]["num_ctx"] == 4096
    assert body["stream"] is False


async def test_complete_retries_on_connect_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"response": "recovered"})

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))
    result = await _adapter(max_retries=5).complete("hi")

    assert result.text == "recovered"
    assert calls["count"] == 3


async def test_complete_raises_llm_unavailable_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))

    with pytest.raises(LLMUnavailableError):
        await _adapter(max_retries=3).complete("hi")

    assert calls["count"] == 3


async def test_complete_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, json={"response": "ok"})

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))
    result = await _adapter(max_retries=5).complete("hi")

    assert result.text == "ok"
    assert calls["count"] == 2


async def test_complete_does_not_retry_on_non_retryable_4xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400, text="bad request")

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))

    with pytest.raises(LLMUnavailableError):
        await _adapter(max_retries=5).complete("hi")

    assert calls["count"] == 1  # never retried a request that will never succeed


async def test_stream_complete_yields_response_chunks_in_order_and_skips_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = _ndjson(
            {"response": "", "thinking": "hmm let me think", "done": False},
            {"response": "", "thinking": "...more thinking", "done": False},
            {"response": "Hello", "done": False},
            {"response": " there", "done": False},
            {"response": "", "done": True, "done_reason": "stop"},
        )
        return httpx.Response(200, content=body)

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))

    chunks = [chunk async for chunk in _adapter().stream_complete("hi")]

    assert chunks == ["Hello", " there"]  # thinking deltas and the empty done-chunk never yielded


async def test_stream_complete_raises_llm_unavailable_when_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))

    with pytest.raises(LLMUnavailableError):
        async for _ in _adapter(max_retries=2, backoff_base_seconds=0.001).stream_complete("hi"):
            pass


async def test_complete_increments_llm_tokens_total(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "hi", "prompt_eval_count": 7, "eval_count": 3})

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))
    before_prompt, before_completion = _tokens_total("prompt"), _tokens_total("completion")

    await _adapter().complete("say hi")

    assert _tokens_total("prompt") == before_prompt + 7
    assert _tokens_total("completion") == before_completion + 3


async def test_stream_complete_increments_llm_tokens_total_from_final_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = _ndjson(
            {"response": "Hello", "done": False},
            {"response": "", "done": True, "prompt_eval_count": 11, "eval_count": 22},
        )
        return httpx.Response(200, content=body)

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))
    before_prompt, before_completion = _tokens_total("prompt"), _tokens_total("completion")

    async for _ in _adapter().stream_complete("hi"):
        pass

    assert _tokens_total("prompt") == before_prompt + 11
    assert _tokens_total("completion") == before_completion + 22


async def test_stream_complete_does_not_retry_on_non_retryable_4xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, text="model not found")

    monkeypatch.setattr(oa.httpx, "AsyncClient", _mock_client_factory(handler))

    with pytest.raises(LLMUnavailableError):
        async for _ in _adapter(max_retries=5).stream_complete("hi"):
            pass

    assert calls["count"] == 1
