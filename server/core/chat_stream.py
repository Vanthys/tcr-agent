"""
core/chat_stream.py — simple pub/sub for live chat streaming.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, List

_subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
_lock = asyncio.Lock()


async def subscribe(message_id: str) -> asyncio.Queue:
    """Register a subscriber queue for a given message_id."""
    queue: asyncio.Queue = asyncio.Queue()
    async with _lock:
        _subscribers[message_id].append(queue)
    return queue


async def unsubscribe(message_id: str, queue: asyncio.Queue) -> None:
    """Remove a subscriber queue."""
    async with _lock:
        queues = _subscribers.get(message_id)
        if not queues:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            _subscribers.pop(message_id, None)


def publish(message_id: str, event: Dict[str, Any]) -> None:
    """Publish an event to all active subscribers."""
    queues = list(_subscribers.get(message_id, []))
    if not queues:
        return
    for queue in queues:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Unbounded queues shouldn't raise, but guard just in case.
            pass
