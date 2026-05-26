import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for live monitoring."""

    def __init__(self):
        # run_id -> set of websocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # "all" channel for global dashboard
        self.global_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, run_id: str = "all"):
        await websocket.accept()
        if run_id == "all":
            self.global_connections.add(websocket)
        else:
            if run_id not in self.active_connections:
                self.active_connections[run_id] = set()
            self.active_connections[run_id].add(websocket)
        logger.info(f"WS connected: {run_id}")

    def disconnect(self, websocket: WebSocket, run_id: str = "all"):
        if run_id == "all":
            self.global_connections.discard(websocket)
        else:
            if run_id in self.active_connections:
                self.active_connections[run_id].discard(websocket)
                if not self.active_connections[run_id]:
                    del self.active_connections[run_id]

    async def broadcast_to_run(self, run_id: str, event: dict):
        """Send event to all watchers of a specific run + global watchers."""
        payload = json.dumps(event)
        dead = set()

        # Run-specific connections
        for ws in self.active_connections.get(run_id, set()):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add((ws, run_id))

        # Global connections (monitor dashboard)
        for ws in self.global_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add((ws, "all"))

        # Cleanup dead connections
        for ws, rid in dead:
            self.disconnect(ws, rid)

    async def broadcast_global(self, event: dict):
        """Send to all global connections."""
        payload = json.dumps(event)
        dead = set()
        for ws in self.global_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.global_connections.discard(ws)


# Singleton
manager = ConnectionManager()
