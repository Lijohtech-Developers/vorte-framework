"""
Vorte AI Module - Schemas
==========================
Pydantic schemas for AI requests, responses, and configuration.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MessageRole(str, Enum):
    """Chat message roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


class FinishReason(str, Enum):
    """Reason why a completion finished."""
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"
    CANCELLED = "cancelled"


class ResponseFormat(str, Enum):
    """Output format modes."""
    TEXT = "text"
    JSON = "json"
    STRUCTURED = "structured"


class RouterStrategy(str, Enum):
    """Model routing strategies."""
    ROUND_ROBIN = "round_robin"
    COST_OPTIMIZED = "cost_optimized"
    LATENCY_OPTIMIZED = "latency_optimized"
    QUALITY_FIRST = "quality_first"
    STATIC = "static"
    LEAST_LOADED = "least_loaded"


# ---------------------------------------------------------------------------
# Chat Messages
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    """A single chat message."""
    role: MessageRole = MessageRole.USER
    content: Union[str, List[Any]] = Field(default="")
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def user(cls, content: str | List[Any], name: str | None = None) -> ChatMessage:
        return cls(role=MessageRole.USER, content=content, name=name)

    @classmethod
    def system(cls, content: str) -> ChatMessage:
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def assistant(cls, content: str, tool_calls: List[Dict[str, Any]] | None = None) -> ChatMessage:
        return cls(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, content: str, tool_call_id: str) -> ChatMessage:
        return cls(role=MessageRole.TOOL, content=content, tool_call_id=tool_call_id)


class ImageContent(BaseModel):
    """Image content block for multimodal messages."""
    type: str = "image_url"
    image_url: Dict[str, str] = Field(default_factory=lambda: {"url": ""})

    @classmethod
    def from_path(cls, path: str) -> ImageContent:
        import base64
        import mimetypes
        mime, _ = mimetypes.guess_type(path)
        mime = mime or "image/png"
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return cls(image_url={"url": f"data:{mime};base64,{data}"})

    @classmethod
    def from_url(cls, url: str) -> ImageContent:
        return cls(image_url={"url": url})

    @classmethod
    def from_base64(cls, data: str, mime: str = "image/png") -> ImageContent:
        return cls(image_url={"url": f"data:{mime};base64,{data}"})


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class CompletionRequest(BaseModel):
    """Universal completion request."""
    model: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    prompt: Optional[str] = None
    system: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop: Optional[List[str]] = None
    stream: bool = False
    response_format: Optional[ResponseFormat] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    seed: Optional[int] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    # Vision / multimodal
    image: Optional[str] = None
    images: Optional[List[str]] = None
    # Structured output
    output_model: Optional[Type[BaseModel]] = Field(default=None, exclude=True)
    # Provider hints
    provider: Optional[str] = None
    fallback_providers: Optional[List[str]] = None
    # Metadata
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EmbeddingRequest(BaseModel):
    """Embedding generation request."""
    texts: List[str]
    model: Optional[str] = None
    input_type: Optional[str] = None  # For Cohere-style embeddings
    encoding_format: str = "float"
    dimensions: Optional[int] = None
    provider: Optional[str] = None
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    """Token usage for a single request."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @property
    def cost(self) -> float:
        """Placeholder – actual cost calculated by CostTracker."""
        return 0.0


class AIResponse(BaseModel):
    """Universal AI response."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    content: str = ""
    model: str = ""
    provider: str = ""
    finish_reason: FinishReason = FinishReason.STOP
    usage: TokenUsage = Field(default_factory=TokenUsage)
    created_at: float = Field(default_factory=time.time)
    request_id: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # Structured output
    structured_output: Optional[Any] = None
    parsed_model: Optional[Type[BaseModel]] = Field(default=None, exclude=True)
    # Tool calls
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def parse(self, model_class: Type[BaseModel]) -> BaseModel:
        """Parse response content into a Pydantic model."""
        if self.structured_output is not None:
            return self.structured_output
        import json
        # Try direct parse
        try:
            return model_class.model_validate_json(self.content)
        except Exception:
            pass
        # Try extracting JSON from markdown code block
        try:
            json_str = self.content.strip()
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                lines = lines[1:]  # skip opening fence
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                json_str = "\n".join(lines)
            return model_class.model_validate_json(json_str)
        except Exception as exc:
            raise ValueError(
                f"Failed to parse AI response into {model_class.__name__}: {exc}"
            ) from exc


class EmbeddingResponse(BaseModel):
    """Embedding generation response."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    embeddings: List[List[float]]
    model: str = ""
    provider: str = ""
    dimensions: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    request_id: str = ""


class StreamChunk(BaseModel):
    """A single chunk in a streaming response."""
    id: str = ""
    content: str = ""
    model: str = ""
    provider: str = ""
    finish_reason: Optional[FinishReason] = None
    usage: Optional[TokenUsage] = None
    delta: Optional[Dict[str, Any]] = None
    request_id: str = ""


# ---------------------------------------------------------------------------
# Configuration Schemas
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    """Configuration for a single AI provider."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    org_id: Optional[str] = None
    default_model: Optional[str] = None
    models: List[str] = Field(default_factory=list)
    timeout: float = 120.0
    max_retries: int = 3
    retry_delay: float = 1.0
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class RoutingConfig(BaseModel):
    """Configuration for model routing."""
    strategy: RouterStrategy = RouterStrategy.STATIC
    rules: List[Dict[str, Any]] = Field(default_factory=list)
    default_provider: Optional[str] = None
    weights: Dict[str, float] = Field(default_factory=dict)


class CostReportEntry(BaseModel):
    """Single entry in a cost report."""
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    request_count: int
    period_start: datetime
    period_end: datetime


class AIConfig(BaseModel):
    """Top-level AI module configuration."""
    default_model: str = "gpt-4o"
    default_provider: str = "openai"
    fallback_providers: List[str] = Field(default_factory=lambda: ["anthropic", "gemini"])
    cache_responses: bool = False
    track_costs: bool = True
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: Optional[float] = None
    timeout: float = 120.0
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    retry_on_failure: bool = True
    max_retries: int = 3
    structured_output_fallback: bool = True
