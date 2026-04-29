"""
OpenClaw Dashboard — WebSocket Connection Manager
=====================================================
Manages WebSocket connections and broadcasts events to all clients.
"""

import json
from datetime import datetime
from typing import List

from fastapi import WebSocket


class ConnectionManager:
    """
    Manages WebSocket connections for real-time dashboard updates.
    
    Broadcasts agent events (step transitions, logs, reasoning)
    to all connected clients.
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._event_history: list = []  # Last N events for new connections
        self._max_history = 100

    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

        # Send recent event history to the new connection
        for event in self._event_history[-20:]:
            try:
                await websocket.send_json(event)
            except Exception:
                break

    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: dict):
        """
        Broadcast an event to all connected clients.
        
        Event format:
        {
            "type": "step_started" | "step_completed" | "step_failed" | 
                    "plan_started" | "plan_completed" | "terminal_output" |
                    "recovery_started" | "notification" | ...,
            "timestamp": "ISO-8601",
            "stepId": "step_1",     (optional)
            "status": "running",    (optional)
            "message": "...",       (optional)
            ...
        }
        """
        # Add timestamp if not present
        if "timestamp" not in event:
            event["timestamp"] = datetime.now().isoformat()

        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # Broadcast to all connected clients
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(event)
            except Exception:
                disconnected.append(connection)

        # Clean up dead connections
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, event: dict):
        """Send an event to a specific client."""
        try:
            await websocket.send_json(event)
        except Exception:
            self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)

    @property
    def event_history(self) -> list:
        return list(self._event_history)
