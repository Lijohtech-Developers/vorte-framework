"""
Vorte AI Module - Base Provider
================================
Abstract base class for all AI providers.
"""

from __future__ import annotations

import abc
from typing import Any, AsyncGenerator, Dict, List, Optional

from vorte.modules.ai.schemas import (
    AIResponse,
    ChatMessage,
    CompletionRequest,
    EmbeddingRequest,
    EmbeddingResponse,
    ProviderConfig,
    StreamChunk,
)


class BaseProvider(abc.ABC):
    """
    Abstract base class that every AI provider must implement.

    Providers translate the universal ``CompletionRequest`` into the
    vendor-specific API call and normalise the response back into
    ``AIResponse``.
    """

    # Subclasses should override these
    name: str = "base"
    default_model: str = ""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.api_key = config.api_key
        self.base_url = (config.base_url or "").rstrip("/")
        self.timeout = config.timeout
        self.max_retries = config.max_retries
        self.retry_delay = config.retry_delay

    # ------------------------------------------------------------------
    # Core API (must be implemented by every provider)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def complete(self, request: CompletionRequest) -> AIResponse:
        """Send a completion request and return a normalised response."""

    @abc.abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncGenerator[StreamChunk, None]:
        """Stream tokens for a completion request."""

    @abc.abstractmethod
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings for the given texts."""

    @abc.abstractmethod
    async def list_models(self) -> List[str]:
        """Return a list of model identifiers available on this provider."""

    # ------------------------------------------------------------------
    # Optional helpers (can be overridden)
    # ------------------------------------------------------------------

    async def validate_api_key(self) -> bool:
        """Check whether the configured API key is valid (lightweight)."""
        return self.api_key is not None and len(self.api_key) > 0

    async def health_check(self) -> Dict[str, Any]:
        """Return a health-check dict for this provider."""
        try:
            key_ok = await self.validate_api_key()
            return {"provider": self.name, "status": "ok" if key_ok else "missing_key"}
        except Exception as exc:
            return {"provider": self.name, "status": "error", "error": str(exc)}

    def model_id(self, model: str | None) -> str:
        """Resolve a model identifier (use default if *model* is ``None``)."""
        return model or self.config.default_model or self.default_model

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
