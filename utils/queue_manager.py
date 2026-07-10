"""
WebSocket Connection Manager for the Live Clinic Queue system.
─────────────────────────────────────────────────────────────
Architecture:
  • One WebSocket "room" per doctor_id.
  • Each room holds a set of active WebSocket connections.
  • A Ping/Pong heartbeat loop detects and evicts dead connections,
    preventing memory leaks in long-running sessions.
"""
import asyncio
import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger("queue.ws")

# How often (seconds) to send a server-side ping to all clients.
HEARTBEAT_INTERVAL = 20


class QueueConnectionManager:
    """
    Thread-safe in-memory WebSocket manager.

    Structure:
        _rooms: { doctor_id: set[WebSocket] }
    """

    def __init__(self):
        # Maps doctor_id → set of active WebSocket connections
        self._rooms: Dict[str, Set[WebSocket]] = {}
        # Tracks the background heartbeat task so we can cancel it gracefully
        self._heartbeat_task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start_heartbeat(self):
        """Launch the background heartbeat coroutine once the event loop is running."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("[WS] Heartbeat loop started.")

    async def _heartbeat_loop(self):
        """
        Periodically ping every connected client.
        If a client's send raises an exception, it is considered dead and removed.
        This is the primary mechanism to prevent zombie connections accumulating in _rooms.
        """
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            dead: list[tuple[str, WebSocket]] = []

            for doctor_id, connections in list(self._rooms.items()):
                for ws in list(connections):
                    try:
                        # WebSocket ping — standard RFC 6455 control frame.
                        await ws.send_text(json.dumps({"event": "heartbeat"}))
                    except Exception:
                        # Connection is dead — mark for removal
                        dead.append((doctor_id, ws))

            # Clean up dead connections outside the iteration
            for doctor_id, ws in dead:
                await self._evict(doctor_id, ws)

    async def _evict(self, doctor_id: str, ws: WebSocket):
        """Remove a single dead/closed connection from a room."""
        if doctor_id in self._rooms:
            self._rooms[doctor_id].discard(ws)
            logger.warning(f"[WS] Evicted dead connection from room '{doctor_id}'. "
                           f"Remaining: {len(self._rooms[doctor_id])}")
            # Clean up empty rooms to reclaim memory
            if not self._rooms[doctor_id]:
                del self._rooms[doctor_id]

    # ── Connection management ─────────────────────────────────────────────

    async def connect(self, doctor_id: str, ws: WebSocket):
        """Accept a new WebSocket connection and register it in the doctor's room."""
        await ws.accept()
        if doctor_id not in self._rooms:
            self._rooms[doctor_id] = set()
        self._rooms[doctor_id].add(ws)
        logger.info(f"[WS] Client joined room '{doctor_id}'. "
                    f"Total: {len(self._rooms[doctor_id])}")

    async def disconnect(self, doctor_id: str, ws: WebSocket):
        """Cleanly remove a connection when a client disconnects intentionally."""
        await self._evict(doctor_id, ws)

    # ── Broadcasting ──────────────────────────────────────────────────────

    async def broadcast(self, doctor_id: str, payload: dict):
        """
        Send a JSON payload to every client watching a specific doctor's queue.
        Dead connections discovered during broadcast are evicted immediately.
        """
        if doctor_id not in self._rooms:
            return  # No clients connected — silent no-op

        dead: list[WebSocket] = []
        message = json.dumps(payload)

        for ws in list(self._rooms[doctor_id]):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self._evict(doctor_id, ws)

    # ── Diagnostics ───────────────────────────────────────────────────────

    def room_size(self, doctor_id: str) -> int:
        """Return how many clients are currently in a doctor's room."""
        return len(self._rooms.get(doctor_id, set()))

    def total_connections(self) -> int:
        """Return the total number of WebSocket connections across all rooms."""
        return sum(len(v) for v in self._rooms.values())


# ── Module-level singleton ────────────────────────────────────────────────────
# Shared across all route modules via import.
queue_manager = QueueConnectionManager()
