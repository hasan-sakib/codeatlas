import asyncio

from app.workers.celery_app import run_in_worker_loop


def test_run_in_worker_loop_reuses_the_same_loop_across_calls() -> None:
    """The whole point of `run_in_worker_loop` over a fresh `asyncio.run()`
    per call: a resource created on one call's loop must still be valid
    on the next call — this is what let a cached asyncpg connection pool
    survive a second Celery task in the same worker process, where a
    fresh-loop-per-task approach broke it (see the module's docstring)."""
    seen_loops: list[int] = []

    async def _record_loop() -> None:
        seen_loops.append(id(asyncio.get_running_loop()))

    run_in_worker_loop(_record_loop)
    run_in_worker_loop(_record_loop)

    assert len(seen_loops) == 2
    assert seen_loops[0] == seen_loops[1]


def test_run_in_worker_loop_returns_the_coroutine_result() -> None:
    async def _add(a: int, b: int) -> int:
        return a + b

    result = run_in_worker_loop(lambda: _add(2, 3))

    assert result == 5
