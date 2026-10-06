"""
app/events.py - Centralized Event System & Server-Sent Events Broadcaster
"""

import json
import time
import asyncio
from typing import List, Any, Dict


class EventBroadcaster:
    """Manages Server-Sent Events (SSE) and WebSocket subscribers and distributes structured events."""
    def __init__(self):
        self.listeners: List[asyncio.Queue] = []
        self.ws_clients: set = set()

    async def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.listeners.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.listeners:
            self.listeners.remove(q)

    async def register_ws(self, ws):
        self.ws_clients.add(ws)

    def unregister_ws(self, ws):
        self.ws_clients.discard(ws)

    async def broadcast(self, event_type: str, data: Any):
        """Broadcast JSON payload to all active SSE queues and WebSocket clients."""
        payload_dict = {
            "type": event_type,
            "event": event_type.lower(),
            "data": data,
            "timestamp": time.time()
        }
        if isinstance(data, dict):
            for k, v in data.items():
                if k not in payload_dict:
                    payload_dict[k] = v
        payload = json.dumps(payload_dict)
        for q in list(self.listeners):
            try:
                await q.put(payload)
            except Exception:
                pass
        dead = []
        for ws in list(self.ws_clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_clients.discard(ws)


# Global singleton broadcaster instance
broadcaster = EventBroadcaster()
