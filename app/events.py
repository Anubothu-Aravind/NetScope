"""
app/events.py - Centralized Event System & Server-Sent Events Broadcaster
"""

import json
import time
import asyncio
from typing import List, Any, Dict


class EventBroadcaster:
    """Manages Server-Sent Events (SSE) subscribers and distributes structured events."""
    def __init__(self):
        self.listeners: List[asyncio.Queue] = []

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.listeners:
            self.listeners.remove(q)

    async def broadcast(self, event_type: str, data: Any):
        """Broadcast JSON payload to all active SSE queues."""
        payload = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        })
        for q in list(self.listeners):
            try:
                await q.put(payload)
            except Exception:
                pass


# Global singleton broadcaster instance
broadcaster = EventBroadcaster()
