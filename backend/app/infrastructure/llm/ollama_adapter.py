import json
from collections.abc import AsyncIterator

import httpx
import structlog
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.observability.metrics import llm_tokens_total
from app.domain.exceptions import LLMUnavailableError
from app.domain.value_objects.llm_completion_result import LLMCompletionResult

logger = structlog.get_logger(__name__)

# Ollama's /api/generate wraps `prompt` in a chat template
# (<|im_start|>user\n...<|im_end|>\n<|im_start|>assistant\n) before
# tokenizing — verified directly: a prompt whose raw text tokenizes to 8
# tokens via token_utils.count_tokens reported prompt_eval_count=18 from
# a real Ollama call. This reserves headroom for that wrapping when a
# caller budgets a prompt against num_ctx; deliberately generous since
# the exact overhead can shift across Ollama/model template versions.
PROMPT_TEMPLATE_OVERHEAD_TOKENS = 32

_RETRYABLE_STATUS_CODES = frozenset({500, 502, 503, 504})


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return False


class OllamaAdapter:
    """`LLMPort` implementation backed by a local Ollama instance.

    Real-API findings this adapter's design is built on (verified by hand
    against a live `qwen3:4b` Ollama instance, not assumed from docs):
    - Qwen3's "thinking" trace and the final answer are separate JSON
      fields (`thinking` vs `response`) on every /api/generate response,
      streaming or not — this adapter reads only `response` and never
      forwards `thinking`, so a chain-of-thought never reaches the caller.
      Attempting to disable thinking via the `think` request field proved
      unreliable in this environment (hung on /api/generate, silently
      ignored — with the <think> block leaking into content — on
      /api/chat), so this deliberately does not send `think` at all and
      relies on the response/thinking field split instead.
    - Ollama's server-launch default context window (verified: 4096) is
      far smaller than the model's advertised maximum (262144) — every
      request sets `options.num_ctx` explicitly rather than relying on
      the server default.
    - `max_tokens`/`temperature` map to `options.num_predict`/
      `options.temperature` — not top-level request fields.
    - `num_predict` bounds thinking + answer tokens combined, not just the
      answer. Verified directly: a trivial "say hello in 3 words" prompt
      with `max_tokens=500` consumed the entire budget on thinking and
      returned `text=""` with `finish_reason="length"` — no answer at
      all. `max_tokens=1024` was enough headroom (827 tokens used, natural
      `finish_reason="stop"`). Callers (Module 13's generate_answer node)
      should budget max_tokens generously — 1024 is a floor for this
      model with thinking on, not a safe default for longer/more complex
      prompts. This is a real operational constraint of Qwen3's default
      thinking behavior combined with this environment's inability to
      reliably disable it (see above); it is not something this adapter
      can paper over without either fighting an unreliable request field
      or mutating caller-supplied prompts, both rejected as out of scope
      for an adapter whose job is to faithfully expose Ollama's API.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "qwen3:4b",
        timeout_s: float = 120.0,
        max_retries: int = 3,
        num_ctx: int = 8192,
        backoff_base_seconds: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._num_ctx = num_ctx
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds

    def _retryer(self) -> AsyncRetrying:
        return AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(
                multiplier=self._backoff_base_seconds, min=self._backoff_base_seconds
            ),
            retry=retry_if_exception(_is_retryable),
        )

    def _build_payload(
        self, prompt: str, max_tokens: int, temperature: float, *, stream: bool
    ) -> dict[str, object]:
        return {
            "model": self._model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_ctx": self._num_ctx,
            },
        }

    async def complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> LLMCompletionResult:
        payload = self._build_payload(prompt, max_tokens, temperature, stream=False)
        try:
            data: dict[str, object] = await self._retryer()(self._post_once, payload)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            raise LLMUnavailableError(
                f"Ollama unavailable after {self._max_retries} attempt(s): {exc}"
            ) from exc

        result = LLMCompletionResult(
            text=str(data.get("response", "")),
            prompt_tokens=int(data.get("prompt_eval_count", 0)),  # type: ignore[call-overload]
            completion_tokens=int(data.get("eval_count", 0)),  # type: ignore[call-overload]
            finish_reason=str(data.get("done_reason", "unknown")),
        )
        llm_tokens_total.labels(direction="prompt").inc(result.prompt_tokens)
        llm_tokens_total.labels(direction="completion").inc(result.completion_tokens)
        return result

    async def _post_once(self, payload: dict[str, object]) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            result: dict[str, object] = response.json()
            return result

    async def stream_complete(
        self, prompt: str, *, max_tokens: int = 1024, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        payload = self._build_payload(prompt, max_tokens, temperature, stream=True)
        client = httpx.AsyncClient(timeout=self._timeout_s)

        # Retries only cover establishing the connection and receiving a
        # response with a non-error status — once real text has started
        # streaming to the caller, a retry would replay/duplicate output,
        # so a failure past that point is raised directly instead.
        try:
            response: httpx.Response = await self._retryer()(self._open_stream, client, payload)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            await client.aclose()
            raise LLMUnavailableError(
                f"Ollama stream unavailable after {self._max_retries} attempt(s): {exc}"
            ) from exc

        try:
            async for line in response.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                text = chunk.get("response", "")
                if text:
                    yield text
                if chunk.get("done"):
                    # Only Ollama's final NDJSON line (done=true) carries
                    # prompt_eval_count/eval_count — every earlier chunk
                    # omits them entirely, verified directly against a
                    # live streaming call.
                    llm_tokens_total.labels(direction="prompt").inc(
                        chunk.get("prompt_eval_count", 0)
                    )
                    llm_tokens_total.labels(direction="completion").inc(chunk.get("eval_count", 0))
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama stream failed mid-response: {exc}") from exc
        finally:
            await response.aclose()
            await client.aclose()

    async def _open_stream(
        self, client: httpx.AsyncClient, payload: dict[str, object]
    ) -> httpx.Response:
        # `client.send(..., stream=True)` returns as soon as headers
        # arrive, without waiting for the body — verified directly: the
        # first NDJSON line lands in ~0.2ms on a real Ollama call, versus
        # ~10s for the first non-thinking `response` chunk on the same
        # call (see class docstring). raise_for_status() is safe to call
        # here since HTTP status is known from headers alone.
        request = client.build_request("POST", f"{self._base_url}/api/generate", json=payload)
        response = await client.send(request, stream=True)
        response.raise_for_status()
        return response
