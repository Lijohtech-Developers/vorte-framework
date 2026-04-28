"""
Vorte Sockets Module - Main Module
====================================
WebSocket support with rooms, presence, and AI streaming.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vorte.core.module import Module, ModuleMeta, ModulePriority
from vorte.core.response import success_response
from vorte.modules.sockets.manager import WebSocketManager


class SocketModule(Module):
    """
    WebSocket module with rooms, broadcasting, and presence tracking.
    """

    meta = ModuleMeta(
        name="sockets",
        version="1.0.0",
        description="Real-time WebSocket communication with rooms and presence",
        priority=ModulePriority.ROUTES,
    )

    def __init__(self):
        super().__init__()
        self.manager: Optional[WebSocketManager] = None
        self._router = APIRouter(tags=["WebSocket"])

    def register(self, app) -> None:
        self.manager = WebSocketManager()
        if hasattr(app, 'container'):
            app.container.register_instance(WebSocketManager, self.manager)
        self._setup_routes(app)

    def _setup_routes(self, app) -> None:
        # Stats endpoint
        @app.get("/sockets/stats")
        async def ws_stats():
            return success_response(self.manager.get_stats())

        # Expose emit on the app for easy use from anywhere
        async def emit_event(event: str, data: Any = None, room: Optional[str] = None):
            return await self.manager.emit(event, data, room=room)
        app.emit = emit_event

    async def health_check(self) -> Dict[str, Any]:
        stats = self.manager.get_stats() if self.manager else {}
        return {"module": self.meta.name, "status": "healthy", "connections": stats.get("total_connections", 0)}
