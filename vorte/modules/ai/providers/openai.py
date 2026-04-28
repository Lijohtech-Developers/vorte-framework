"""
Vorte AI Module - OpenAI Provider
===================================
Provider implementation for the OpenAI API (including Azure OpenAI-compatible
endpoints and any OpenAI-compatible server, e.g. Ollama, vLLM, LiteLLM).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from vorte.modules.ai.providers.base import BaseProvider
from vorte.modules.ai.schemas import (
    AIResponse,
    ChatMessage,
    CompletionRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    FinishReason,
    ImageContent,
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)

logger = logging.getLogger("vorte.ai.providers.openai")

# Map our FinishReason to OpenAI's finish_reason strings and back
_OPENAI_FINISH_MAP = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "content_filter": FinishReason.CONTENT_FILTER,
}

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(BaseProvider):
    """OpenAI API provider."""

    name: str = "openai"
    default_model: str = _DEFAULT_MODEL

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        self.base_url = self.base_url or _DEFAULT_BASE_URL

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if self.config.org_id:
            h["OpenAI-Organization"] = self.config.org_id
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
                    logger.warning("OpenAI HTTP %s (attempt %d/%d): %s",
                                   exc.response.status_code, attempt, self.max_retries, body[:300])
                    if exc.response.status_code in (401, 403):
                        raise RuntimeError(f"OpenAI auth error: {body[:200]}") from exc
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
            raise RuntimeError(f"OpenAI request failed after {self.max_retries} retries") from last_exc

    # ------------------------------------------------------------------
    # Message translation
    # ------------------------------------------------------------------

    def _translate_messages(self, request: CompletionRequest) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []

        # System prompt
        if request.system:
            messages.append({"role": "system", "content": request.system})

        # Existing messages
        for msg in request.messages:
            m: Dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                m["name"] = msg.name
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                m["tool_calls"] = msg.tool_calls
            messages.append(m)

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
            content_parts: List[Any] = []
            # Find last user message to augment
            last_user_idx = None
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]["role"] == "user":
                    last_user_idx = i
                    break
            if last_user_idx is not None:
                text = messages[last_user_idx].get("content", "")
                if isinstance(text, str):
                    content_parts.append({"type": "text", "text": text})
            for img in images:
                if img.startswith(("http://", "https://")):
                    content_parts.append({"type": "image_url", "image_url": {"url": img}})
                else:
                    # Treat as local file path
                    content_parts.append(ImageContent.from_path(img).model_dump())
            if content_parts:
                messages[last_user_idx]["content"] = content_parts

        return messages

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def complete(self, request: CompletionRequest) -> AIResponse:
        model = self.model_id(request.model)
        messages = self._translate_messages(request)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop"] = request.stop
        if request.tools:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.frequency_penalty is not None:
            payload["frequency_penalty"] = request.frequency_penalty
        if request.presence_penalty is not None:
            payload["presence_penalty"] = request.presence_penalty
        if request.response_format:
            if request.response_format.value == "json":
                payload["response_format"] = {"type": "json_object"}

        payload.update(self.config.extra_params)

        data = await self._post("chat/completions", payload)

        choice = data["choices"][0]
        message = choice["message"]
        usage_info = data.get("usage", {})

        return AIResponse(
            id=data.get("id", ""),
            content=message.get("content", "") or "",
            model=data.get("model", model),
            provider=self.name,
            finish_reason=_OPENAI_FINISH_MAP.get(choice.get("finish_reason", "stop"), FinishReason.STOP),
            usage=TokenUsage(
                prompt_tokens=usage_info.get("prompt_tokens", 0),
                completion_tokens=usage_info.get("completion_tokens", 0),
                total_tokens=usage_info.get("total_tokens", 0),
            ),
            request_id=request.request_id,
            tool_calls=message.get("tool_calls"),
        )

    async def stream(self, request: CompletionRequest) -> AsyncGenerator[StreamChunk, None]:
        model = self.model_id(request.model)
        messages = self._translate_messages(request)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        payload.update(self.config.extra_params)

        import httpx

        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", url, json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        yield StreamChunk(
                            content="",
                            model=model,
                            provider=self.name,
                            finish_reason=FinishReason.STOP,
                            request_id=request.request_id,
                        )
                        return
                    try:
                        chunk_data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choice = chunk_data["choices"][0]
                    delta = choice.get("delta", {})
                    yield StreamChunk(
                        id=chunk_data.get("id", ""),
                        content=delta.get("content", "") or "",
                        model=chunk_data.get("model", model),
                        provider=self.name,
                        finish_reason=_OPENAI_FINISH_MAP.get(choice.get("finish_reason")),
                        delta=delta if delta else None,
                        request_id=request.request_id,
                    )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = self.model_id(request.model) or "text-embedding-3-small"
        payload: Dict[str, Any] = {
            "model": model,
            "input": request.texts,
        }
        if request.dimensions:
            payload["dimensions"] = request.dimensions
        payload.update(self.config.extra_params)

        data = await self._post("embeddings", payload)

        embeddings: List[List[float]] = []
        for item in sorted(data["data"], key=lambda x: x["index"]):
            embeddings.append(item["embedding"])

        usage_info = data.get("usage", {})
        return EmbeddingResponse(
            embeddings=embeddings,
            model=data.get("model", model),
            provider=self.name,
            dimensions=len(embeddings[0]) if embeddings else 0,
            usage=TokenUsage(
                prompt_tokens=usage_info.get("prompt_tokens", 0),
                total_tokens=usage_info.get("total_tokens", 0),
            ),
            request_id=request.request_id,
        )

    async def list_models(self) -> List[str]:
        import httpx
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]

    async def validate_api_key(self) -> bool:
        try:
            models = await self.list_models()
            return len(models) > 0
        except Exception:
            return False
