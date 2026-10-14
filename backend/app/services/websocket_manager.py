import asyncio
import logging
from typing import List, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections and broadcasts real-time fraud alerts.
    Isolates slow/disconnected clients with per-connection timeouts so broadcast
    failures can never block the application or corrupt committed database transactions.
    """

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Active connections: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Active connections: %d", len(self.active_connections))

    async def broadcast(self, message: Dict[str, Any], timeout: float = 1.0):
        """
        Broadcast JSON payload to all active clients safely.
        Catches transport errors and pruning dead or slow sockets.
        """
        if not self.active_connections:
            return

        dead: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await asyncio.wait_for(connection.send_json(message), timeout=timeout)
            except Exception as exc:
                logger.warning("WebSocket transmission failed or timed out: %s", exc)
                dead.append(connection)

        for d in dead:
            self.disconnect(d)

    @property
    def client_count(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()
