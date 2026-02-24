"""Event fan-out for USB license/admin lock SSE stream."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
_subscribers_lock = asyncio.Lock()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def subscribe() -> asyncio.Queue[dict[str, Any]]:
    """Register an SSE subscriber queue."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
    async with _subscribers_lock:
        _subscribers.add(queue)
    return queue


async def unsubscribe(queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Unregister an SSE subscriber queue."""
    async with _subscribers_lock:
        _subscribers.discard(queue)


async def publish(event: str, data: dict[str, Any] | None = None) -> None:
    """Publish an event to all subscribers.

    Slow subscribers are dropped if their queue is full.
    """
    payload = {
        "event": event,
        "data": {**(data or {}), "emitted_at": _utcnow_iso()},
    }
    async with _subscribers_lock:
        subscribers = list(_subscribers)

    stale_queues: list[asyncio.Queue[dict[str, Any]]] = []
    for queue in subscribers:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            stale_queues.append(queue)

    if stale_queues:
        async with _subscribers_lock:
            for queue in stale_queues:
                _subscribers.discard(queue)
