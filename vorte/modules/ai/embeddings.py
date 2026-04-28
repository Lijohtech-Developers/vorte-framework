"""
Vorte AI Module - Embedding Generation
========================================
Unified embedding interface across providers with batching, caching,
and dimension normalisation.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from vorte.modules.ai.providers.base import BaseProvider
from vorte.modules.ai.providers.registry import ProviderRegistry
from vorte.modules.ai.schemas import (
    EmbeddingRequest,
    EmbeddingResponse,
    TokenUsage,
)

logger = logging.getLogger("vorte.ai.embeddings")

# Default batch sizes per provider (some APIs have limits)
_DEFAULT_BATCH_SIZES: Dict[str, int] = {
    "openai": 2048,
    "anthropic": 1,  # not supported – placeholder
    "gemini": 1,     # one-at-a-time API
    "mistral": 64,
}


class EmbeddingCache:
    """
    Simple in-memory embedding cache.

    For production use, replace with Redis / persistent store.
    """

    def __init__(self, max_size: int = 10_000) -> None:
        self._cache: Dict[str, List[float]] = {}
        self._max_size = max_size

    @staticmethod
    def _key(text: str, model: str, dimensions: Optional[int]) -> str:
        raw = f"{model}:{dimensions}:{text}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, text: str, model: str, dimensions: Optional[int] = None) -> Optional[List[float]]:
        k = self._key(text, model, dimensions)
        return self._cache.get(k)

    def put(self, text: str, model: str, embedding: List[float], dimensions: Optional[int] = None) -> None:
        if len(self._cache) >= self._max_size:
            # Evict oldest entries (simple FIFO)
            keys_to_remove = list(self._cache.keys())[: self._max_size // 4]
            for k in keys_to_remove:
                del self._cache[k]
        self._cache[self._key(text, model, dimensions)] = embedding

    def get_many(
        self, texts: List[str], model: str, dimensions: Optional[int] = None,
    ) -> tuple[List[Optional[List[float]]], List[int]]:
        """Return cached embeddings and indices of cache misses."""
        results: List[Optional[List[float]]] = []
        miss_indices: List[int] = []
        for i, text in enumerate(texts):
            emb = self.get(text, model, dimensions)
            results.append(emb)
            if emb is None:
                miss_indices.append(i)
        return results, miss_indices

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class EmbeddingEngine:
    """
    Unified embedding engine.

    Handles:
    * Provider selection for embedding requests
    * Automatic batching according to provider limits
    * In-memory caching (replaceable)
    * Dimension normalisation / reduction
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        cache: Optional[EmbeddingCache] = None,
        default_provider: str = "openai",
        default_model: str = "text-embedding-3-small",
    ) -> None:
        self._registry = registry
        self._cache = cache or EmbeddingCache()
        self._default_provider = default_provider
        self._default_model = default_model

    def configure(
        self,
        default_provider: Optional[str] = None,
        default_model: Optional[str] = None,
        cache_max_size: Optional[int] = None,
    ) -> None:
        if default_provider is not None:
            self._default_provider = default_provider
        if default_model is not None:
            self._default_model = default_model
        if cache_max_size is not None:
            self._cache = EmbeddingCache(max_size=cache_max_size)

    def _resolve_provider(
        self, provider_name: Optional[str], model: Optional[str]
    ) -> tuple[BaseProvider, str]:
        """Determine the provider and model for an embedding request."""
        name = provider_name or self._default_provider
        provider = self._registry.get(name)
        if provider is None:
            raise ValueError(f"Embedding provider '{name}' not found in registry.")

        resolved_model = model or self._default_model
        return provider, resolved_model

    @staticmethod
    def _batch_size(provider: BaseProvider) -> int:
        return _DEFAULT_BATCH_SIZES.get(provider.name, 64)

    async def embed(
        self,
        text: str,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        dimensions: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[float]:
        """Get an embedding vector for a single text."""
        results = await self.embed_many(
            [text],
            model=model,
            provider=provider,
            dimensions=dimensions,
            use_cache=use_cache,
        )
        return results[0]

    async def embed_many(
        self,
        texts: List[str],
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        dimensions: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[List[float]]:
        """
        Get embeddings for multiple texts.

        * Uses cache for hits.
        * Batches misses according to provider limits.
        * Optionally normalises dimensions.
        """
        if not texts:
            return []

        provider_obj, resolved_model = self._resolve_provider(provider, model)

        # Check cache
        if use_cache:
            cached, miss_indices = self._cache.get_many(texts, resolved_model, dimensions)
            if not miss_indices:
                return [emb for emb in cached]  # type: ignore[list-item]
        else:
            cached: List[Optional[List[float]]] = [None] * len(texts)
            miss_indices = list(range(len(texts)))

        # Fetch misses in batches
        miss_texts = [texts[i] for i in miss_indices]
        all_embeddings: Dict[int, List[float]] = {}

        batch_size = self._batch_size(provider_obj)
        for batch_start in range(0, len(miss_texts), batch_size):
            batch = miss_texts[batch_start : batch_start + batch_size]
            request = EmbeddingRequest(
                texts=batch,
                model=resolved_model,
                dimensions=dimensions,
                request_id="",
            )
            try:
                response = await provider_obj.embed(request)
            except NotImplementedError:
                # Provider doesn't support embeddings – fall back
                raise NotImplementedError(
                    f"Provider '{provider_obj.name}' does not support embeddings. "
                    f"Use a provider that has an embeddings API (e.g. 'openai', 'mistral')."
                )

            for j, emb in enumerate(response.embeddings):
                original_idx = miss_indices[batch_start + j]
                all_embeddings[original_idx] = emb
                # Store in cache
                if use_cache:
                    self._cache.put(
                        texts[original_idx], resolved_model, emb, dimensions
                    )

        # Merge
        result: List[List[float]] = []
        for i in range(len(texts)):
            if cached[i] is not None:
                result.append(cached[i])
            elif i in all_embeddings:
                result.append(all_embeddings[i])
            else:
                raise RuntimeError(f"Missing embedding for text at index {i}")

        return result

    async def similarity(
        self,
        text_a: str,
        text_b: str,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> float:
        """Compute cosine similarity between two texts."""
        import math

        embs = await self.embed_many([text_a, text_b], model=model, provider=provider)
        a, b = embs[0], embs[1]

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def clear_cache(self) -> None:
        self._cache.clear()

    @property
    def cache_size(self) -> int:
        return len(self._cache)
