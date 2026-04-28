"""
Vorte AI Module - Anthropic Provider
=====================================
Provider implementation for the Anthropic Messages API (Claude family).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from vorte.modules.ai.providers.base import BaseProvider
from vorte.modules.ai.schemas import (
    AIResponse,
    CompletionRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    FinishReason,
    ImageContent,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)

logger = logging.getLogger("vorte.ai.providers.anthropic")

_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_ANTHROPIC_VERSION = "2023-06-01"

_ANTHROPIC_FINISH_MAP = {
    "end_turn": FinishReason.STOP,
    "max_tokens": FinishReason.LENGTH,
    "tool_use": FinishReason.TOOL_CALLS,
    "stop_sequence": FinishReason.STOP,
}


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API provider."""

    name: str = "anthropic"
    default_model: str = _DEFAULT_MODEL

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = self.base_url or _DEFAULT_BASE_URL
        self.anthropic_version = config.extra_params.get(
            "anthropic_version", _ANTHROPIC_VERSION
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": self.anthropic_version,
        }
        h.update(self.config.extra_headers)
        return h

    async def _post(self, path: str, payload: dict) -> dict:
        import httpx

        url = f"{self.base_url}/{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            last_exc: Optional[Exception] = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    resp = await client.post(url, json=payload, headers=self._headers())
                    resp.raise_for_status()
                    return resp.json()
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text
                    logger.warning("Anthropic HTTP %s (attempt %d/%d): %s",
                                   exc.response.status_code, attempt, self.max_retries, body[:300])
                    if exc.response.status_code in (401, 403):
                        raise RuntimeError(f"Anthropic auth error: {body[:200]}") from exc
                    if exc.response.status_code >= 500 or exc.response.status_code == 429:
                        last_exc = exc
                        if attempt < self.max_retries:
                            await asyncio.sleep(self.retry_delay * attempt)
                        continue
                    raise
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                    last_exc = exc
                    if attempt < self.max_retries:
                        await asyncio.sleep(self.retry_delay * attempt)
                        continue
                    raise
            raise RuntimeError(
                f"Anthropic request failed after {self.max_retries} retries"
            ) from last_exc

    # ------------------------------------------------------------------
    # Message translation
    # ------------------------------------------------------------------

    def _translate_messages(self, request: CompletionRequest) -> tuple:
        """
        Return (system_str, messages_list) adapted for Anthropic.

        Anthropic expects a separate ``system`` parameter and the messages
        list uses ``content`` blocks for text + images.
        """
        system = request.system or ""
        messages: List[Dict[str, Any]] = []

        for msg in request.messages:
            role = msg.role.value
            if role == "system":
                system = system + ("\n" if system else "") + msg.content
                continue

            if role == "assistant" and msg.tool_calls:
                # Anthropic expects tool_use content blocks
                content_blocks: List[Dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    fn = tc.get("function", {})
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": json.loads(fn.get("arguments", "{}")),
                    })
                messages.append({"role": role, "content": content_blocks})
                continue

            if role == "tool":
                # Anthropic expects tool_result content block
                content_blocks = [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id or "",
                    "content": msg.content,
                }]
                messages.append({"role": "user", "content": content_blocks})
                continue

            messages.append({"role": role, "content": msg.content})

        # Prompt shorthand
        if request.prompt and not messages:
            messages.append({"role": "user", "content": request.prompt})

        # Vision: add image(s)
        images: List[str] = []
        if request.image:
            images.append(request.image)
        if request.images:
            images.extend(request.images)

        if images and messages:
            # Find last user message to augment with image blocks
            last_user_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "user":
                    last_user_idx = i
                    break
            if last_user_idx is not None:
                existing = messages[last_user_idx].get("content", "")
                content_blocks: List[Any] = []
                if isinstance(existing, str) and existing:
                    content_blocks.append({"type": "text", "text": existing})
                for img in images:
                    if img.startswith(("http://", "https://")):
                        content_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": img,
                            },
                        })
                    else:
                        import base64
                        import mimetypes
                        mime, _ = mimetypes.guess_type(img)
                        mime = mime or "image/png"
                        with open(img, "rb") as f:
                            data = base64.b64encode(f.read()).decode()
                        content_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": data,
                            },
                        })
                if content_blocks:
                    messages[last_user_idx]["content"] = content_blocks

        return system, messages

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def complete(self, request: CompletionRequest) -> AIResponse:
        model = self.model_id(request.model)
        system, messages = self._translate_messages(request)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
        }
        if system:
            payload["system"] = system
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop_sequences"] = request.stop
        if request.tools:
            # Translate tools to Anthropic format
            anthropic_tools = []
            for tool in request.tools:
                fn = tool.get("function", {})
                anthropic_tools.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                })
            payload["tools"] = anthropic_tools
        if request.seed is not None:
            payload["seed"] = request.seed
        payload.update(self.config.extra_params)

        data = await self._post("messages", payload)

        # Extract text content
        content_parts = data.get("content", [])
        text = ""
        tool_calls = None
        for block in content_parts:
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        usage_info = data.get("usage", {})
        return AIResponse(
            id=data.get("id", ""),
            content=text,
            model=data.get("model", model),
            provider=self.name,
            finish_reason=_ANTHROPIC_FINISH_MAP.get(
                data.get("stop_reason", "end_turn"), FinishReason.STOP
            ),
            usage=TokenUsage(
                prompt_tokens=usage_info.get("input_tokens", 0),
                completion_tokens=usage_info.get("output_tokens", 0),
                total_tokens=usage_info.get("input_tokens", 0) + usage_info.get("output_tokens", 0),
            ),
            request_id=request.request_id,
            tool_calls=tool_calls,
        )

    async def stream(self, request: CompletionRequest) -> AsyncGenerator[StreamChunk, None]:
        model = self.model_id(request.model)
        system, messages = self._translate_messages(request)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        payload.update(self.config.extra_params)

        import httpx

        url = f"{self.base_url}/messages"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", url, json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield StreamChunk(
                                id=event.get("message", {}).get("id", ""),
                                content=delta.get("text", ""),
                                model=model,
                                provider=self.name,
                                request_id=request.request_id,
                            )

                    elif event_type == "message_stop":
                        yield StreamChunk(
                            content="",
                            model=model,
                            provider=self.name,
                            finish_reason=FinishReason.STOP,
                            request_id=request.request_id,
                        )
                        return

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        # Anthropic does not have a native embeddings API.
        # This is a placeholder that raises a clear error.
        raise NotImplementedError(
            "Anthropic does not provide a native embeddings API. "
            "Please use the 'openai' or 'mistral' provider for embeddings."
        )

    async def list_models(self) -> List[str]:
        # Anthropic does not have a list-models endpoint.
        # Return known Claude models.
        return [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]

    async def validate_api_key(self) -> bool:
        """Validate key by sending a minimal request."""
        try:
            await self.complete(CompletionRequest(
                prompt="Hi",
                max_tokens=1,
            ))
            return True
        except Exception:
            return False
