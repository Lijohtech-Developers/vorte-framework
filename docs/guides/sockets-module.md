# Sockets Module

WebSocket management with rooms, broadcasting, and authentication.

## Setup

```python
from vorte import SocketModule

app.register(SocketModule())
```

## Features

- **Connection Manager** -- Track all active WebSocket connections
- **Rooms** -- Group connections into rooms for targeted broadcasting
- **Broadcasting** -- Send messages to all connections or specific rooms
- **Authentication** -- Authenticate WebSocket connections
- **Lifecycle Hooks** -- Handle connect, disconnect, and message events

## Usage

```python
@app.socket("/ws/chat")
async def chat_websocket(websocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Echo: {data}")
```

## Connection Manager

```python
from vorte.modules.sockets import ConnectionManager

manager = ConnectionManager()

# Join a room
await manager.join("room_123", websocket)

# Broadcast to room
await manager.broadcast("room_123", {"message": "Hello room!"})

# Leave room
await manager.leave("room_123", websocket)
```
