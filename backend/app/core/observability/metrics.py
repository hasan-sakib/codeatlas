"""Module-level singletons — imported once per process, matching every
other `prometheus_client` metric definition convention (registering the
same metric name twice in one process raises). `http_request_duration_seconds`
and friends are NOT defined here: `instrumentation.py`'s
`Instrumentator()` provides those automatically.
"""

from prometheus_client import Counter, Gauge, Histogram

retrieval_duration_seconds = Histogram(
    "retrieval_duration_seconds",
    "Duration of a single retrieval-pipeline stage",
    labelnames=["stage"],  # dense | sparse | fuse | rerank
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "LLM tokens processed",
    labelnames=["direction"],  # prompt | completion
)

cache_hits_total = Counter(
    "cache_hits_total",
    "Cache hits",
    labelnames=["cache_name"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Cache misses",
    labelnames=["cache_name"],
)

# --- Defined for the indexing pipeline, no live call site yet ---
#
# Module 21's RunIndexingPipelineUseCase (app/application/use_cases/
# indexing/run_indexing_pipeline.py) and CeleryIndexingTaskDispatcher now
# execute real indexing jobs, but neither observes this histogram yet —
# left as a follow-up rather than bundled into that change. Defined here
# so the eventual instrumentation has a metric to emit into without
# needing a Monitoring-module change alongside its own; see
# docs/modules/monitoring.md.
indexing_job_duration_seconds = Histogram(
    "indexing_job_duration_seconds",
    "Duration of an indexing-pipeline stage",
    labelnames=["stage"],
)

celery_queue_depth = Gauge(
    "celery_queue_depth",
    "Pending tasks per Celery queue",
    labelnames=["queue"],
)
