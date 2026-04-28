"""
Vorte AI Module
=================
Provider-agnostic AI integration with streaming, embeddings, structured
output, and cost tracking.

Usage::

    from vorte.modules.ai import AIModule, AIClient, ChatMessage

    # Register with the app
    app.use(AIModule, config={
        "providers": {
            "openai": {"api_key": "sk-..."},
        },
    })

    # Use the client
    ai: AIClient = app.ai
    response = await ai.complete("Hello, world!")
"""

from vorte.modules.ai.module import AIModule
from vorte.modules.ai.client import AIClient
from vorte.modules.ai.cost_tracker import CostTracker, UsageRecord
from vorte.modules.ai.embeddings import EmbeddingEngine, EmbeddingCache
from vorte.modules.ai.providers.base import BaseProvider
from vorte.modules.ai.providers.registry import ProviderRegistry
from vorte.modules.ai.providers.openai import OpenAIProvider
from vorte.modules.ai.providers.anthropic import AnthropicProvider
from vorte.modules.ai.providers.gemini import GeminiProvider
from vorte.modules.ai.providers.mistral import MistralProvider
from vorte.modules.ai.streaming import (
    StreamSession,
    StreamAggregator,
    SSEParser,
    WebSocketStream,
    collect_stream,
)
from vorte.modules.ai.schemas import (
    # Enums
    MessageRole,
    FinishReason,
    ResponseFormat,
    RouterStrategy,
    # Messages
    ChatMessage,
    ImageContent,
    # Requests
    CompletionRequest,
    EmbeddingRequest,
    # Responses
    AIResponse,
    TokenUsage,
    StreamChunk,
    EmbeddingResponse,
    # Configuration
    AIConfig,
    ProviderConfig,
    RoutingConfig,
    CostReportEntry,
)

__all__ = [
    # Module
    "AIModule",
    # Client
    "AIClient",
    # Cost tracking
    "CostTracker",
    "UsageRecord",
    # Embeddings
    "EmbeddingEngine",
    "EmbeddingCache",
    # Providers
    "BaseProvider",
    "ProviderRegistry",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "MistralProvider",
    # Streaming
    "StreamSession",
    "StreamAggregator",
    "SSEParser",
    "WebSocketStream",
    "collect_stream",
    # Schemas – Enums
    "MessageRole",
    "FinishReason",
    "ResponseFormat",
    "RouterStrategy",
    # Schemas – Messages
    "ChatMessage",
    "ImageContent",
    # Schemas – Requests
    "CompletionRequest",
    "EmbeddingRequest",
    # Schemas – Responses
    "AIResponse",
    "TokenUsage",
    "StreamChunk",
    "EmbeddingResponse",
    # Schemas – Configuration
    "AIConfig",
    "ProviderConfig",
    "RoutingConfig",
    "CostReportEntry",
]
