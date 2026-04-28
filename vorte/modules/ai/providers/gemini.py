"""
Vorte AI Module - Google Gemini Provider
==========================================
Provider implementation for the Google Gemini API (generateContent & embeddings).
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
    ProviderConfig,
    StreamChunk,
    TokenUsage,
)

logger = logging.getLogger("vorte.ai.providers.gemini")

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-2.0-flash"

_GEMINI_FINISH_MAP = {
    "STOP": FinishReason.STOP,
    "MAX_TOKENS": FinishReason.LENGTH,
    "SAFETY": FinishReason.CONTENT_FILTER,
    "RECITATION": FinishReason.CONTENT_FILTER,
    "OTHER": FinishReason.ERROR,
}


class GeminiProvider(BaseProvider):
    """Google Gemini API provider."""

    name: str = "gemini"
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
        }
        if self.api_key:
            # Gemini uses api_key as a query param for some endpoints,
            # but can also be sent via x-goog-api-key header.
            h["x-goog-api-key"] = self.api_key
        h.update(self.config.extra_headers)
        return h

    def _url(self, action: str, model: str, stream: bool = False) -> str:
        base = f"{self.base_url}/models/{model}:{action}"
        if stream:
            base += "?alt=sse"
        if self.api_key:
            sep = "&" if "?" in base else "?"
            base += f"{sep}key={self.api_key}"
        return base

    async def _post(self, path: str, payload: dict, stream: bool = False):
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            last_exc: Optional[Exception] = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    if stream:
                        async with client.stream(
                            "POST", path, json=payload, headers=self._headers()
                        ) as resp:
                            resp.raise_for_status()
                            return resp
                    else:
                        resp = await client.post(path, json=payload, headers=self._headers())
                        resp.raise_for_status()
                        return resp.json()
                except httpx.HTTPStatusError as exc:
                    body = exc.response.text
                    logger.warning("Gemini HTTP %s (attempt %d/%d): %s",
                                   exc.response.status_code, attempt, self.max_retries, body[:300])
                    if exc.response.status_code in (401, 403):
                        raise RuntimeError(f"Gemini auth error: {body[:200]}") from exc
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
            raise RuntimeError(f"Gemini request failed after {self.max_retries} retries") from last_exc

    # ------------------------------------------------------------------
    # Message translation
    # ------------------------------------------------------------------

    def _translate_messages(self, request: CompletionRequest) -> tuple:
        """
        Return (system_instruction, contents) for the Gemini API.

        Gemini uses ``contents`` (role + parts) and an optional
        ``systemInstruction`` field.
        """
        system_instruction = None
        if request.system:
            system_instruction = {"parts": [{"text": request.system}]}

        contents: List[Dict[str, Any]] = []

        for msg in request.messages:
            role = msg.role.value
            if role == "system":
                if system_instruction:
                    system_instruction["parts"][0]["text"] += "\n" + msg.content
                else:
                    system_instruction = {"parts": [{"text": msg.content}]}
                continue

            # Gemini expects "user" or "model" (not "assistant")
            if role == "assistant":
                role = "model"

            if isinstance(msg.content, list):
                # Already structured content blocks
                parts = msg.content
            else:
                parts = [{"text": msg.content}]

            contents.append({"role": role, "parts": parts})

        # Prompt shorthand
        if request.prompt and not contents:
            parts: List[Dict[str, Any]] = [{"text": request.prompt}]
            # Vision: add image(s)
            images: List[str] = []
            if request.image:
                images.append(request.image)
            if request.images:
                images.extend(request.images)
            for img in images:
                if img.startswith(("http://", "https://")):
                    parts.append({"file_data": {"mime_type": "image/png", "file_uri": img}})
                else:
                    import base64
                    import mimetypes
                    mime, _ = mimetypes.guess_type(img)
                    mime = mime or "image/png"
                    with open(img, "rb") as f:
                        data = base64.b64encode(f.read()).decode()
                    parts.append({"inline_data": {"mime_type": mime, "data": data}})
            contents.append({"role": "user", "parts": parts})

        return system_instruction, contents

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def complete(self, request: CompletionRequest) -> AIResponse:
        model = self.model_id(request.model)
        system_instruction, contents = self._translate_messages(request)

        payload: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        # Generation config
        gen_config: Dict[str, Any] = {}
        if request.temperature is not None:
            gen_config["temperature"] = request.temperature
        if request.max_tokens is not None:
            gen_config["maxOutputTokens"] = request.max_tokens
        if request.top_p is not None:
            gen_config["topP"] = request.top_p
        if request.top_k is not None:
            gen_config["topK"] = request.top_k
        if request.stop:
            gen_config["stopSequences"] = request.stop
        if request.seed is not None:
            gen_config["seed"] = request.seed
        if request.response_format and request.response_format.value == "json":
            gen_config["responseMimeType"] = "application/json"
        if gen_config:
            payload["generationConfig"] = gen_config

        # Tools
        if request.tools:
            gemini_tools = []
            for tool in request.tools:
                fn = tool.get("function", {})
                gemini_tools.append({
                    "function_declarations": [{
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {}),
                    }],
                })
            payload["tools"] = gemini_tools

        payload.update(self.config.extra_params)

        url = self._url("generateContent", model)
        data = await self._post(url, payload)

        candidate = data.get("candidates", [{}])[0]
        finish_reason = _GEMINI_FINISH_MAP.get(
            candidate.get("finishReason", "STOP"), FinishReason.STOP
        )

        content_parts = candidate.get("content", {}).get("parts", [])
        text = ""
        for part in content_parts:
            if "text" in part:
                text += part["text"]

        usage_meta = data.get("usageMetadata", {})
        return AIResponse(
            id=data.get("id", ""),
            content=text,
            model=model,
            provider=self.name,
            finish_reason=finish_reason,
            usage=TokenUsage(
                prompt_tokens=usage_meta.get("promptTokenCount", 0),
                completion_tokens=usage_meta.get("candidatesTokenCount", 0),
                total_tokens=usage_meta.get("totalTokenCount", 0),
            ),
            request_id=request.request_id,
        )

    async def stream(self, request: CompletionRequest) -> AsyncGenerator[StreamChunk, None]:
        model = self.model_id(request.model)
        system_instruction, contents = self._translate_messages(request)

        payload: Dict[str, Any] = {"contents": contents}
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        gen_config: Dict[str, Any] = {}
        if request.temperature is not None:
            gen_config["temperature"] = request.temperature
        if request.max_tokens is not None:
            gen_config["maxOutputTokens"] = request.max_tokens
        if gen_config:
            payload["generationConfig"] = gen_config
        payload.update(self.config.extra_params)

        url = self._url("streamGenerateContent", model, stream=True)
        response = await self._post(url, payload, stream=True)

        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            try:
                chunk_data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            candidates = chunk_data.get("candidates", [{}])
            if not candidates:
                continue
            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    finish = _GEMINI_FINISH_MAP.get(
                        candidate.get("finishReason")
                    )
                    yield StreamChunk(
                        content=part["text"],
                        model=model,
                        provider=self.name,
                        finish_reason=finish,
                        request_id=request.request_id,
                    )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = self.model_id(request.model) or "text-embedding-004"

        url = self._url("embedContent", model)
        results: List[List[float]] = []
        total_prompt_tokens = 0

        for text in request.texts:
            payload = {
                "model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
            }
            if request.dimensions:
                payload["outputDimensionality"] = request.dimensions

            data = await self._post(url.replace(f"models/{model}:", ""), payload)

            embedding = data.get("embedding", {}).get("values", [])
            results.append(embedding)

            usage_meta = data.get("usageMetadata", {})
            total_prompt_tokens += usage_meta.get("promptTokenCount", 0)

        return EmbeddingResponse(
            embeddings=results,
            model=model,
            provider=self.name,
            dimensions=len(results[0]) if results else 0,
            usage=TokenUsage(prompt_tokens=total_prompt_tokens, total_tokens=total_prompt_tokens),
            request_id=request.request_id,
        )

    async def list_models(self) -> List[str]:
        import httpx

        url = f"{self.base_url}/models"
        params: Dict[str, str] = {}
        if self.api_key:
            params["key"] = self.api_key
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"].replace("models/", "") for m in data.get("models", [])]

    async def validate_api_key(self) -> bool:
        try:
            models = await self.list_models()
            return len(models) > 0
        except Exception:
            return False
