"""
Vorte AI Module - Streaming Support
=====================================
SSE (Server-Sent Events) and WebSocket streaming helpers for AI responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
)

from vorte.modules.ai.schemas import (
    AIResponse,
    CompletionRequest,
    FinishReason,
    StreamChunk,
    TokenUsage,
)

logger = logging.getLogger("vorte.ai.streaming")


# ---------------------------------------------------------------------------
# Callback types
# ---------------------------------------------------------------------------

OnChunkCallback = Callable[[StreamChunk], Any]
OnCompleteCallback = Callable[[AIResponse], Any]
OnErrorCallback = Callable[[Exception], Any]


@dataclass
class StreamSession:
    """
    Represents an active streaming session.

    Aggregates chunks into a full response and provides hooks for
    real-time processing.
    """

    request_id: str = ""
    model: str = ""
    provider: str = ""
    chunks: List[StreamChunk] = field(default_factory=list)
    full_text: str = ""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    is_finished: bool = False
    error: Optional[Exception] = None

    # Callbacks
    on_chunk: Optional[OnChunkCallback] = None
    on_complete: Optional[OnCompleteCallback] = None
    on_error: Optional[OnErrorCallback] = None

    # Accumulated tool calls
    _tool_call_accumulator: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, repr=False
    )

    def append(self, chunk: StreamChunk) -> None:
        """Append a chunk and update aggregate state."""
        self.chunks.append(chunk)
        if chunk.content:
            self.full_text += chunk.content
        if chunk.model:
            self.model = chunk.model
        if chunk.provider:
            self.provider = chunk.provider
        if chunk.usage:
            self.total_prompt_tokens += chunk.usage.prompt_tokens
            self.total_completion_tokens += chunk.usage.completion_tokens
        if chunk.finish_reason is not None:
            self.is_finished = True

        # Invoke callback
        if self.on_chunk:
            try:
                result = self.on_chunk(chunk)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception as exc:
                logger.warning("on_chunk callback error: %s", exc)

    def to_response(self) -> AIResponse:
        """Build a final ``AIResponse`` from the accumulated chunks."""
        return AIResponse(
            id=self.chunks[0].id if self.chunks else "",
            content=self.full_text,
            model=self.model,
            provider=self.provider,
            finish_reason=self._final_finish_reason(),
            usage=TokenUsage(
                prompt_tokens=self.total_prompt_tokens,
                completion_tokens=self.total_completion_tokens,
                total_tokens=self.total_prompt_tokens + self.total_completion_tokens,
            ),
            request_id=self.request_id,
        )

    def _final_finish_reason(self) -> FinishReason:
        for chunk in reversed(self.chunks):
            if chunk.finish_reason is not None:
                return chunk.finish_reason
        return FinishReason.STOP if self.is_finished else FinishReason.ERROR


# ---------------------------------------------------------------------------
# Stream aggregator
# ---------------------------------------------------------------------------

class StreamAggregator:
    """
    Consumes an async generator of ``StreamChunk`` and yields them while
    maintaining an aggregated view.

    Usage::

        session = StreamSession(request_id="abc")
        aggregator = StreamAggregator(provider.complete(request))
        async for chunk in aggregator:
            print(chunk.content, end="")
        print(f"\\nFull text: {aggregator.session.full_text}")
    """

    def __init__(
        self,
        chunk_stream: AsyncGenerator[StreamChunk, None],
        session: Optional[StreamSession] = None,
    ) -> None:
        self._stream = chunk_stream
        self.session = session or StreamSession()
        self._started = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> StreamChunk:
        if not self._started:
            self._started = True
            self._task = asyncio.ensure_future(self._consume())
        if not self._buffer:
            if self._done:
                raise StopAsyncIteration
            await self._event.wait()
            self._event.clear()
        if not self._buffer and self._done:
            raise StopAsyncIteration
        return self._buffer.pop(0)

    async def _consume(self) -> None:
        self._buffer: List[StreamChunk] = []
        self._event = asyncio.Event()
        self._done = False
        try:
            async for chunk in self._stream:
                self._buffer.append(chunk)
                self.session.append(chunk)
                self._event.set()
        except Exception as exc:
            self.session.error = exc
            if self.session.on_error:
                try:
                    self.session.on_error(exc)
                except Exception:
                    pass
        finally:
            self._done = True
            self._event.set()

    @property
    def text(self) -> str:
        """Current aggregated text."""
        return self.session.full_text

    @property
    def is_finished(self) -> bool:
        return self.session.is_finished or self._done


# ---------------------------------------------------------------------------
# SSE Parser
# ---------------------------------------------------------------------------

class SSEParser:
    """
    Parser for Server-Sent Events (SSE) streams.

    Can parse a raw byte stream or an async line iterator into
    structured events.
    """

    def __init__(self) -> None:
        self._buffer: str = ""

    def feed(self, data: str) -> List[Dict[str, str]]:
        """Feed raw data and return parsed events."""
        self._buffer += data
        return self._parse()

    def _parse(self) -> List[Dict[str, str]]:
        events: List[Dict[str, str]] = []
        lines = self._buffer.split("\n")
        self._buffer = lines.pop()  # keep incomplete last line in buffer

        current_event: Dict[str, str] = {}
        for line in lines:
            line = line.strip()
            if not line:
                if current_event:
                    events.append(current_event)
                    current_event = {}
                continue
            if line.startswith(":"):
                # Comment – skip
                continue
            if line.startswith("event:"):
                current_event["event"] = line[6:].strip()
            elif line.startswith("data:"):
                key = "data"
                if "data" in current_event:
                    key = "data_1"  # secondary data
                    i = 1
                    while key in current_event:
                        i += 1
                        key = f"data_{i}"
                current_event[key] = line[5:].strip()
            elif line.startswith("id:"):
                current_event["id"] = line[3:].strip()
            elif line.startswith("retry:"):
                current_event["retry"] = line[6:].strip()

        if current_event:
            events.append(current_event)
        return events

    async def parse_async_lines(self, line_iter) -> AsyncGenerator[Dict[str, str], None]:
        """Parse events from an async line iterator."""
        async for line in line_iter:
            events = self.feed(line)
            for event in events:
                yield event


# ---------------------------------------------------------------------------
# WebSocket streaming
# ---------------------------------------------------------------------------

class WebSocketStream:
    """
    Adapts a WebSocket connection for streaming AI responses.

    Expects the server to send JSON frames with ``content`` and optionally
    ``finish_reason`` fields.
    """

    def __init__(self, ws) -> None:
        self._ws = ws

    async def stream(self) -> AsyncGenerator[StreamChunk, None]:
        """Yield StreamChunks from WebSocket messages."""
        while True:
            try:
                msg = await self._ws.recv()
                if isinstance(msg, bytes):
                    msg = msg.decode("utf-8")
                if not msg:
                    continue

                data = json.loads(msg)

                if data.get("type") == "end" or data.get("finish_reason"):
                    yield StreamChunk(
                        id=data.get("id", ""),
                        content=data.get("content", ""),
                        model=data.get("model", ""),
                        provider=data.get("provider", ""),
                        finish_reason=FinishReason(data.get("finish_reason", "stop")),
                    )
                    return

                yield StreamChunk(
                    id=data.get("id", ""),
                    content=data.get("content", ""),
                    model=data.get("model", ""),
                    provider=data.get("provider", ""),
                    delta=data,
                )
            except Exception as exc:
                logger.error("WebSocket stream error: %s", exc)
                yield StreamChunk(
                    content="",
                    finish_reason=FinishReason.ERROR,
                )
                return


# ---------------------------------------------------------------------------
# Convenience: collect all chunks into a full response
# ---------------------------------------------------------------------------

async def collect_stream(
    stream: AsyncGenerator[StreamChunk, None],
) -> AIResponse:
    """Consume an entire stream and return the aggregated AIResponse."""
    session = StreamSession()
    aggregator = StreamAggregator(stream, session)
    async for _ in aggregator:
        pass  # drain
    return session.to_response()
