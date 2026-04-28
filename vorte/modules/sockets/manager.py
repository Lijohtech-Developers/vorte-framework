"""
Vorte Sockets Module - WebSocket Connection Manager
=====================================================
Manages WebSocket connections, rooms, broadcasting, and presence.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect


@dataclass
class ConnectionInfo:
    """Information about a WebSocket connection."""
    ws: WebSocket
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    rooms: Set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=lambda: __import__('time').time())


class RoomManager:
    """Manages WebSocket rooms for broadcasting."""

    def __init__(self):
        self._rooms: Dict[str, Dict[str, ConnectionInfo]] = defaultdict(dict)

    async def join(self, room_id: str, connection: ConnectionInfo) -> None:
        """Add a connection to a room."""
        self._rooms[room_id][id(connection)] = connection
        connection.rooms.add(room_id)

    async def leave(self, room_id: str, connection: ConnectionInfo) -> None:
        """Remove a connection from a room."""
        self._rooms[room_id].pop(id(connection), None)
        connection.rooms.discard(room_id)
        if not self._rooms[room_id]:
            del self._rooms[room_id]

    async def broadcast(self, room_id: str, message: Any, exclude: Optional[ConnectionInfo] = None) -> int:
        """Broadcast a message to all connections in a room. Returns count of recipients."""
        room = self._rooms.get(room_id, {})
        data = json.dumps(message) if not isinstance(message, str) else message
        count = 0
        for conn_id, conn in list(room.items()):
            if conn is exclude:
                continue
            try:
                await conn.ws.send_text(data)
                count += 1
            except Exception:
                await self.leave(room_id, conn)
        return count

    async def broadcast_bytes(self, room_id: str, data: bytes, exclude: Optional[ConnectionInfo] = None) -> int:
        """Broadcast binary data to all connections in a room."""
        room = self._rooms.get(room_id, {})
        count = 0
        for conn_id, conn in list(room.items()):
            if conn is exclude:
                continue
            try:
                await conn.ws.send_bytes(data)
                count += 1
            except Exception:
                await self.leave(room_id, conn)
        return count

    def get_room_members(self, room_id: str) -> List[Dict[str, Any]]:
        """Get all members in a room."""
        room = self._rooms.get(room_id, {})
        return [
            {"user_id": c.user_id, "email": c.user_email}
            for c in room.values() if c.user_id
        ]

    def get_room_count(self, room_id: str) -> int:
        """Get the number of connections in a room."""
        return len(self._rooms.get(room_id, {}))

    def get_all_rooms(self) -> Dict[str, int]:
        """Get all rooms with their member counts."""
        return {name: len(members) for name, members in self._rooms.items()}


class PresenceTracker:
    """Tracks online/presence status of users."""

    def __init__(self):
        self._online: Dict[str, Set[str]] = defaultdict(set)  # channel -> user_ids
        self._user_rooms: Dict[str, Set[str]] = defaultdict(set)  # user_id -> channels

    async def track(self, user_id: str, channel: str) -> None:
        """Track a user as online in a channel."""
        self._online[channel].add(user_id)
        self._user_rooms[user_id].add(channel)

    async def untrack(self, user_id: str, channel: str) -> None:
        """Remove a user from a channel."""
        self._online[channel].discard(user_id)
        self._user_rooms[user_id].discard(channel)

    def get_online(self, channel: str) -> List[str]:
        """Get all online user IDs in a channel."""
        return list(self._online.get(channel, set()))

    def is_online(self, user_id: str, channel: str) -> bool:
        """Check if a user is online in a channel."""
        return user_id in self._online.get(channel, set())

    def get_user_channels(self, user_id: str) -> List[str]:
        """Get all channels a user is tracked in."""
        return list(self._user_rooms.get(user_id, set()))

    def get_total_online(self, channel: str) -> int:
        """Get total online count for a channel."""
        return len(self._online.get(channel, set()))


class WebSocketManager:
    """
    Central WebSocket manager combining rooms, presence, and broadcasting.
    """

    def __init__(self):
        self._connections: Dict[int, ConnectionInfo] = {}
        self.rooms = RoomManager()
        self.presence = PresenceTracker()

    async def connect(self, ws: WebSocket, user_id: Optional[str] = None, user_email: Optional[str] = None) -> ConnectionInfo:
        """Accept a WebSocket connection and track it."""
        await ws.accept()
        conn = ConnectionInfo(ws=ws, user_id=user_id, user_email=user_email)
        self._connections[id(conn)] = conn
        if user_id:
            await self.presence.track(user_id, "global")
        return conn

    async def disconnect(self, conn: ConnectionInfo) -> None:
        """Remove a connection and clean up."""
        # Leave all rooms
        for room_id in list(conn.rooms):
            await self.rooms.leave(room_id, conn)
        # Remove presence
        if conn.user_id:
            for channel in self.presence.get_user_channels(conn.user_id):
                await self.presence.untrack(conn.user_id, channel)
        self._connections.pop(id(conn), None)

    async def send(self, conn: ConnectionInfo, message: Any) -> None:
        """Send a message to a specific connection."""
        data = json.dumps(message) if not isinstance(message, str) else message
        await conn.ws.send_text(data)

    async def send_bytes(self, conn: ConnectionInfo, data: bytes) -> None:
        """Send binary data to a specific connection."""
        await conn.ws.send_bytes(data)

    async def emit(self, event: str, data: Any = None, room: Optional[str] = None, exclude: Optional[ConnectionInfo] = None) -> int:
        """Emit an event to a room or all connections."""
        message = {"event": event, "data": data}
        if room:
            return await self.rooms.broadcast(room, message, exclude=exclude)
        # Broadcast to all connections
        count = 0
        for conn in list(self._connections.values()):
            if conn is exclude:
                continue
            try:
                await self.send(conn, message)
                count += 1
            except Exception:
                await self.disconnect(conn)
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket statistics."""
        return {
            "total_connections": len(self._connections),
            "rooms": self.rooms.get_all_rooms(),
            "online_by_channel": {
                ch: self.presence.get_total_online(ch)
                for ch in self._online_channels()
            },
        }

    def _online_channels(self) -> List[str]:
        return list(set(
            ch for uid_channels in self.presence._user_rooms.values()
            for ch in uid_channels
        ))
