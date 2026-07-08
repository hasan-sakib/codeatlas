import json
from collections.abc import AsyncGenerator
from uuid import UUID

from redis.asyncio import Redis

from app.api.streaming.events import DoneEvent, ProgressEvent, SSEEventName


# The wire contract a future indexing-progress publisher must follow —
# no such publisher exists yet (the indexing pipeline isn't wired up as
# an orchestrated whole; Module 6 only registered
# NullIndexingTaskDispatcher). Documented here since this is the one
# real consumer of the channel until that publisher lands.
#
# Channel: f"indexing:progress:{job_id}"
# Progress message:  {"stage": str, "percent": float | null, "message": str | null}
# Terminal message:  {"event": "done"}
def _channel_name(job_id: UUID) -> str:
    return f"indexing:progress:{job_id}"


async def subscribe_to_indexing_progress(
    job_id: UUID, redis_client: Redis
) -> AsyncGenerator[tuple[SSEEventName, ProgressEvent | DoneEvent], None]:
    channel = _channel_name(job_id)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue  # e.g. the "subscribe" confirmation message

            data = json.loads(message["data"])
            if data.get("event") == "done":
                yield (SSEEventName.DONE, DoneEvent())
                return

            yield (
                SSEEventName.PROGRESS,
                ProgressEvent(
                    stage=data["stage"],
                    percent=data.get("percent"),
                    message=data.get("message"),
                ),
            )
    finally:
        await pubsub.unsubscribe(channel)
        # redis-py's PubSub.aclose has no type stub.
        await pubsub.aclose()  # type: ignore[no-untyped-call]
