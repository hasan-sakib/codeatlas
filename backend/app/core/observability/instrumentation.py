from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup_prometheus_instrumentator(app: FastAPI) -> None:
    """Wires automatic `http_request_duration_seconds`/`http_requests_total`
    (labeled by handler/method/status) and exposes them at `/metrics`.

    `should_exclude_streaming_duration=True`: the chat SSE endpoint
    (`POST .../messages`) can legitimately stay open for many seconds
    while the LLM streams tokens — without this flag, that full duration
    would land in `http_request_duration_seconds`, badly skewing the
    histogram buckets for what's otherwise meant to read as ordinary
    REST latency. Per-stage LLM/retrieval timing is covered separately
    by `retrieval_duration_seconds`/`llm_tokens_total` in `metrics.py`.
    """
    Instrumentator(should_exclude_streaming_duration=True).instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )
