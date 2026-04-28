"""
Vorte AI Module - Universal AI Client
=======================================
The main public-facing interface for the AI module.

Provides a single, provider-agnostic API::

    ai = AIClient(registry, config)

    # Simple completion
    response = await ai.complete("Hello, world!")

    # Structured output
    result = await ai.complete("Extract name", output=Person)

    # Chat
    response = await ai.chat([
        {"role": "user", "content": "What is 2+2?"},
    ])

    # Streaming
    async for chunk in ai.stream("Tell me a story"):
        print(chunk.content, end="")

    # Embeddings
    vec = await ai.embed("some text")
    vecs = await ai.embed_many(["a", "b", "c"])

    # Vision
    response = await ai.complete("Describe this image", image="photo.jpg")
"""

from __future__ import annotations

import json
import logging
import time
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel

from vorte.modules.ai.cost_tracker import CostTracker
from vorte.modules.ai.embeddings import EmbeddingCache, EmbeddingEngine
from vorte.modules.ai.providers.base import BaseProvider
from vorte.modules.ai.providers.registry import ProviderRegistry
from vorte.modules.ai.schemas import (
    AIConfig,
    AIResponse,
    ChatMessage,
    CompletionRequest,
    EmbeddingResponse,
    ProviderConfig,
    ResponseFormat,
    RouterStrategy,
    RoutingConfig,
    StreamChunk,
)
from vorte.modules.ai.streaming import (
    StreamAggregator,
    StreamSession,
    collect_stream,
)

logger = logging.getLogger("vorte.ai.client")

T = TypeVar("T", bound=BaseModel)


class AIClient:
    """
    Universal, provider-agnostic AI client.

    This is the primary entry point for all AI operations.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        config: Optional[AIConfig] = None,
        cost_tracker: Optional[CostTracker] = None,
        embedding_engine: Optional[EmbeddingEngine] = None,
    ) -> None:
        self._registry = registry
        self._config = config or AIConfig()
        self._cost_tracker = cost_tracker or CostTracker()
        self._embedding_engine = embedding_engine or EmbeddingEngine(
            registry=registry,
            default_provider=self._config.default_provider,
            default_model="text-embedding-3-small",
        )
        self._response_cache: Dict[str, AIResponse] = {}
        self._max_cache = 1000

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        *,
        fallback: Optional[List[str]] = None,
        router: Optional[Dict[str, Any]] = None,
        default_model: Optional[str] = None,
        default_provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        cache_responses: Optional[bool] = None,
        track_costs: Optional[bool] = None,
        budget_limit: Optional[float] = None,
    ) -> None:
        """Configure client settings at runtime."""
        if fallback is not None:
            self._registry.set_fallback_chain(fallback)
        if router is not None:
            strategy = RouterStrategy(router.get("strategy", "static"))
            self._registry.set_strategy(strategy)
            rules = router.get("rules", [])
            # Rules could include model-based routing; store for reference
            self._config.routing = RoutingConfig(strategy=strategy, rules=rules)
        if default_model is not None:
            self._config.default_model = default_model
        if default_provider is not None:
            self._config.default_provider = default_provider
        if temperature is not None:
            self._config.temperature = temperature
        if max_tokens is not None:
            self._config.max_tokens = max_tokens
        if cache_responses is not None:
            self._config.cache_responses = cache_responses
        if track_costs is not None:
            self._config.track_costs = track_costs
        if budget_limit is not None:
            self._cost_tracker.set_budget(budget_limit)

    # ------------------------------------------------------------------
    # Universal completion
    # ------------------------------------------------------------------

    async def complete(
        self,
        prompt: str | List[ChatMessage] | None = None,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        response_format: Optional[ResponseFormat] = None,
        provider: Optional[str] = None,
        image: Optional[str] = None,
        images: Optional[List[str]] = None,
        output: Optional[Type[T]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AIResponse | T:
        """
        Universal completion – the primary entry point.

        Can be used for:
        * Simple text generation: ``ai.complete("Hello")``
        * Chat: ``ai.complete(messages=[...])``
        * Structured output: ``ai.complete("extract", output=MyModel)``
        * Vision: ``ai.complete("describe", image="path")``

        Returns an ``AIResponse`` by default, or a parsed Pydantic model
        if ``output`` is specified.
        """
        # Build request
        if isinstance(prompt, list):
            messages = prompt
            prompt_text = None
        else:
            prompt_text = prompt
            messages = []

        request = CompletionRequest(
            model=model or self._config.default_model,
            messages=messages,
            prompt=prompt_text,
            system=system or self._config.system_prompt if hasattr(self._config, "system_prompt") else system,
            temperature=temperature if temperature is not None else self._config.temperature,
            max_tokens=max_tokens or self._config.max_tokens,
            top_p=top_p or self._config.top_p,
            stop=stop,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
            provider=provider or self._config.default_provider,
            image=image,
            images=images,
            metadata=metadata or {},
            **kwargs,
        )

        # Structured output preparation
        if output is not None:
            request.response_format = ResponseFormat.JSON
            # Inject schema instructions into system prompt
            schema_json = output.model_json_schema()
            schema_instruction = (
                f"\n\nYou MUST respond with valid JSON matching this schema:\n"
                f"```json\n{json.dumps(schema_json, indent=2)}\n```\n"
                f"Respond ONLY with the JSON object, no other text."
            )
            if request.system:
                request.system += schema_instruction
            else:
                request.system = schema_instruction
            request.output_model = output  # type: ignore[assignment]

        # Cache check
        if self._config.cache_responses:
            cache_key = self._cache_key(request)
            if cache_key in self._response_cache:
                cached = self._response_cache[cache_key]
                if output is not None:
                    return cached.parse(output)
                return cached

        # Execute with fallback
        response = await self._execute_with_fallback(request)

        # Cache store
        if self._config.cache_responses:
            cache_key = self._cache_key(request)
            self._response_cache[cache_key] = response
            if len(self._response_cache) > self._max_cache:
                # Evict oldest entries
                keys = list(self._response_cache.keys())
                for k in keys[: self._max_cache // 4]:
                    del self._response_cache[k]

        # Track costs
        if self._config.track_costs:
            self._cost_tracker.record(response)

        # Structured output parsing
        if output is not None:
            try:
                return response.parse(output)
            except Exception as exc:
                if self._config.structured_output_fallback:
                    logger.warning(
                        "Structured output parse failed, retrying: %s", exc
                    )
                    retry_request = CompletionRequest(
                        model=response.model,
                        messages=[
                            ChatMessage.system(
                                "The previous response was not valid JSON. "
                                "You MUST respond with ONLY a valid JSON object, "
                                f"matching this schema:\n{json.dumps(schema_json, indent=2)}"
                            ),
                            ChatMessage.user(
                                f"Original request: {prompt_text or 'chat'}\n\n"
                                f"Your previous (invalid) response:\n{response.content}"
                            ),
                        ],
                        temperature=0.0,
                        max_tokens=request.max_tokens,
                        provider=request.provider,
                        response_format=ResponseFormat.JSON,
                        metadata=request.metadata,
                    )
                    retry_response = await self._execute_with_fallback(retry_request)
                    if self._config.track_costs:
                        self._cost_tracker.record(retry_response)
                    return retry_response.parse(output)
                raise

        return response

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[ChatMessage] | List[Dict[str, str]] | None = None,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        provider: Optional[str] = None,
        **kwargs,
    ) -> AIResponse:
        """Send a chat completion request with a list of messages."""
        normalised: List[ChatMessage] = []
        for msg in (messages or []):
            if isinstance(msg, ChatMessage):
                normalised.append(msg)
            elif isinstance(msg, dict):
                normalised.append(ChatMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    name=msg.get("name"),
                ))
            else:
                raise TypeError(f"Invalid message type: {type(msg)}")

        return await self.complete(  # type: ignore[arg-type]
            prompt=normalised,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            provider=provider,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def stream(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        on_chunk: Optional[Callable[[StreamChunk], Any]] = None,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream tokens for a prompt. Yields ``StreamChunk`` objects."""
        return self._stream_impl(
            prompt=prompt,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            provider=provider,
            on_chunk=on_chunk,
            **kwargs,
        )

    async def _stream_impl(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        on_chunk: Optional[Callable[[StreamChunk], Any]] = None,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        request = CompletionRequest(
            model=model or self._config.default_model,
            prompt=prompt,
            system=system,
            temperature=temperature if temperature is not None else self._config.temperature,
            max_tokens=max_tokens or self._config.max_tokens,
            provider=provider or self._config.default_provider,
            stream=True,
            **kwargs,
        )

        provider_instance = self._registry.resolve_provider(request)
        session = StreamSession(
            request_id=request.request_id,
            model=request.model or "",
            provider=provider_instance.name,
            on_chunk=on_chunk,
        )

        try:
            self._registry.increment_load(provider_instance.name)
            start = time.monotonic()
            async for chunk in provider_instance.stream(request):
                yield chunk
                session.append(chunk)
            latency = time.monotonic() - start
            self._registry.record_latency(provider_instance.name, latency)
            # Track costs from accumulated session
            if self._config.track_costs:
                final = session.to_response()
                self._cost_tracker.record(final)
        except Exception as exc:
            logger.error("Streaming error from %s: %s", provider_instance.name, exc)
            if on_chunk:
                error_chunk = StreamChunk(
                    content="",
                    provider=provider_instance.name,
                    finish_reason=FinishReason.ERROR,
                )
                on_chunk(error_chunk)
            raise
        finally:
            self._registry.decrement_load(provider_instance.name)

    async def stream_text(
        self,
        prompt: str,
        **kwargs,
    ) -> str:
        """Stream a completion and return the full accumulated text."""
        chunks = []
        async for chunk in self.stream(prompt, **kwargs):
            chunks.append(chunk.content)
        return "".join(chunks)

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def embed(
        self,
        text: str,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> List[float]:
        """Get an embedding vector for a single text."""
        return await self._embedding_engine.embed(
            text, model=model, provider=provider, dimensions=dimensions,
        )

    async def embed_many(
        self,
        texts: List[str],
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> List[List[float]]:
        """Get embedding vectors for multiple texts."""
        return await self._embedding_engine.embed_many(
            texts, model=model, provider=provider, dimensions=dimensions,
        )

    async def similarity(
        self,
        text_a: str,
        text_b: str,
        **kwargs,
    ) -> float:
        """Compute cosine similarity between two texts."""
        return await self._embedding_engine.similarity(text_a, text_b, **kwargs)

    # ------------------------------------------------------------------
    # Fallback execution
    # ------------------------------------------------------------------

    async def _execute_with_fallback(self, request: CompletionRequest) -> AIResponse:
        """
        Execute a request with automatic fallback on provider failure.
        """
        primary = self._registry.resolve_provider(request)
        fallback_chain = self._registry.get_fallback_chain(exclude=primary.name)

        errors: List[Exception] = []

        for provider_instance in [primary] + fallback_chain:
            request.provider = provider_instance.name
            try:
                self._registry.increment_load(provider_instance.name)
                start = time.monotonic()
                response = await provider_instance.complete(request)
                latency = time.monotonic() - start
                self._registry.record_latency(provider_instance.name, latency)
                self._registry.record_cost(provider_instance.name, 0.0)  # cost tracked separately
                return response
            except Exception as exc:
                errors.append(exc)
                logger.warning(
                    "Provider %s failed for model %s: %s",
                    provider_instance.name,
                    request.model,
                    exc,
                )
                if self._config.retry_on_failure and provider_instance is primary:
                    continue
            finally:
                self._registry.decrement_load(provider_instance.name)

        raise RuntimeError(
            f"All providers failed for model {request.model!r}:\n"
            + "\n".join(f"  - {type(e).__name__}: {e}" for e in errors)
        )

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_key(self, request: CompletionRequest) -> str:
        """Generate a deterministic cache key for a request."""
        import hashlib
        parts = [
            request.provider or "",
            request.model or "",
            request.system or "",
            str(request.temperature),
            str(request.max_tokens),
        ]
        if request.prompt:
            parts.append(request.prompt)
        for msg in request.messages:
            parts.append(f"{msg.role}:{msg.content}")
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()

    def clear_cache(self) -> None:
        self._response_cache.clear()

    # ------------------------------------------------------------------
    # Access to sub-components
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    @property
    def cost_tracker(self) -> CostTracker:
        return self._cost_tracker

    @property
    def embeddings(self) -> EmbeddingEngine:
        return self._embedding_engine

    @property
    def config(self) -> AIConfig:
        return self._config

    # ------------------------------------------------------------------
    # Model introspection
    # ------------------------------------------------------------------

    async def list_models(self, provider: Optional[str] = None) -> Dict[str, List[str]]:
        """List available models, optionally filtered by provider."""
        result: Dict[str, List[str]] = {}
        providers = (
            [self._registry.get(provider)] if provider
            else list(self._registry.get_all().values())
        )
        for p in providers:
            if p is None:
                continue
            try:
                models = await p.list_models()
                result[p.name] = models
            except Exception as exc:
                logger.warning("Failed to list models for %s: %s", p.name, exc)
                result[p.name] = []
        return result

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all registered providers."""
        results: Dict[str, Any] = {}
        for name, provider in self._registry.get_all().items():
            try:
                results[name] = await provider.health_check()
            except Exception as exc:
                results[name] = {"provider": name, "status": "error", "error": str(exc)}
        results["cost_tracker"] = {
            "total_cost": self._cost_tracker.total_cost,
            "total_tokens": self._cost_tracker.total_tokens,
            "total_requests": self._cost_tracker.total_requests,
            "budget_ok": self._cost_tracker.check_budget(),
        }
        return results


# Re-import FinishReason for use in _stream_impl (avoids circular import issue)
from vorte.modules.ai.schemas import FinishReason  # noqa: E402
