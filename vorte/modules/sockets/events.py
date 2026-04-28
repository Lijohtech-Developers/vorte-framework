"""Vorte Sockets Module - Event system over WebSocket."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from vorte.modules.sockets.manager import WebSocketManager


class SocketEventBus:
    """Event bus that bridges app events to WebSocket connections."""

    def __init__(self, ws_manager: WebSocketManager):
        self._ws_manager = ws_manager
        self._handlers: Dict[str, Callable] = {}

    def on(self, event: str) -> Callable:
        """Register an event handler."""
        def decorator(func: Callable) -> Callable:
            self._handlers[event] = func
            return func
        return decorator

    async def handle(self, event: str, data: Any = None) -> Optional[Any]:
        """Handle an incoming event."""
        handler = self._handlers.get(event)
        if handler:
            result = handler(data)
            if hasattr(result, '__await__'):
                return await result
            return result
        return None

    async def broadcast(self, event: str, data: Any = None, room: Optional[str] = None) -> int:
        """Broadcast an event to WebSocket clients."""
        return await self._ws_manager.emit(event, data, room=room)
