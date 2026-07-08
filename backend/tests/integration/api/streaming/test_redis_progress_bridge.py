import asyncio
import json
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.api.streaming.events import DoneEvent, ProgressEvent, SSEEventName
from app.api.streaming.redis_progress_bridge import subscribe_to_indexing_progress

pytestmark = pytest.mark.integration


async def _publish_after_delay(url: str, channel: str, messages: list[dict]) -> None:
    await asyncio.sleep(0.2)  # give subscribe_to_indexing_progress time to subscribe first
    publisher: Redis = Redis.from_url(url)
    for message in messages:
        await publisher.publish(channel, json.dumps(message))
        await asyncio.sleep(0.05)
    await publisher.aclose()


async def test_subscribe_yields_progress_then_done_in_order(
    redis_client: Redis, redis_container
) -> None:
    job_id = uuid4()
    channel = f"indexing:progress:{job_id}"
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"

    publisher_task = asyncio.create_task(
        _publish_after_delay(
            url,
            channel,
            [
                {"stage": "parsing", "percent": 10},
                {"stage": "embedding", "percent": 50},
                {"event": "done"},
            ],
        )
    )

    events = [event async for event in subscribe_to_indexing_progress(job_id, redis_client)]
    await publisher_task

    assert events == [
        (SSEEventName.PROGRESS, ProgressEvent(stage="parsing", percent=10)),
        (SSEEventName.PROGRESS, ProgressEvent(stage="embedding", percent=50)),
        (SSEEventName.DONE, DoneEvent()),
    ]


async def test_subscribe_stops_generator_at_done_without_waiting_for_more(
    redis_client: Redis, redis_container
) -> None:
    job_id = uuid4()
    channel = f"indexing:progress:{job_id}"
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"

    publisher_task = asyncio.create_task(
        _publish_after_delay(
            url,
            channel,
            [{"event": "done"}, {"stage": "should_never_be_seen", "percent": 100}],
        )
    )

    events = [event async for event in subscribe_to_indexing_progress(job_id, redis_client)]
    # Generator returns at "done"; wait for the (harmless) trailing publish too.
    await publisher_task

    assert events == [(SSEEventName.DONE, DoneEvent())]


async def test_subscribe_only_receives_messages_for_its_own_job_channel(
    redis_client: Redis, redis_container
) -> None:
    job_id = uuid4()
    other_job_id = uuid4()
    url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"

    async def publish_both() -> None:
        await asyncio.sleep(0.2)
        publisher: Redis = Redis.from_url(url)
        await publisher.publish(
            f"indexing:progress:{other_job_id}", json.dumps({"stage": "irrelevant", "percent": 1})
        )
        await publisher.publish(
            f"indexing:progress:{job_id}", json.dumps({"stage": "parsing", "percent": 5})
        )
        await publisher.publish(f"indexing:progress:{job_id}", json.dumps({"event": "done"}))
        await publisher.aclose()

    publisher_task = asyncio.create_task(publish_both())

    events = [event async for event in subscribe_to_indexing_progress(job_id, redis_client)]
    await publisher_task

    assert events == [
        (SSEEventName.PROGRESS, ProgressEvent(stage="parsing", percent=5)),
        (SSEEventName.DONE, DoneEvent()),
    ]
