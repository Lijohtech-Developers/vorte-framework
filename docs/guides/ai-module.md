# AI Module

Multi-provider AI integration with cost tracking, streaming, embeddings, and intelligent routing.

## Setup

```python
from vorte import AIModule

app.register(AIModule())
```

## Configuration

```env
VORTE_AI_DEFAULT_MODEL=gpt-4
VORTE_AI_TRACK_COSTS=true
VORTE_AI_MAX_TOKENS=4096
VORTE_AI_TEMPERATURE=0.7
```

Configure providers:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
```

## Supported Providers

| Provider | Models | Streaming | Embeddings | Vision |
|----------|--------|-----------|------------|--------|
| OpenAI | GPT-4, GPT-3.5, etc. | Yes | Yes | Yes |
| Anthropic | Claude 3.5, etc. | Yes | No | Yes |
| Gemini | Gemini Pro, etc. | Yes | Yes | Yes |
| Mistral | Mistral, Mixtral | Yes | Yes | Yes |

## Provider Registry & Routing Strategies

```python
# 6 routing strategies:
# STATIC         - Always use configured provider
# ROUND_ROBIN    - Distribute across providers
# COST_OPTIMIZED - Choose cheapest provider
# LEAST_LOADED   - Route to least busy provider
# LATENCY_OPTIMIZED - Route to fastest provider
# QUALITY_FIRST  - Route to highest-quality provider
```

The registry tracks latency, cost, and load metrics per provider with sliding windows for adaptive routing.

## Features

- **Streaming** -- SSE-based token streaming for all providers
- **Embeddings** -- Text embeddings for vector search (OpenAI, Gemini, Mistral)
- **Cost Tracking** -- Automatic cost tracking per request with `AIMeta` in responses
- **Fallback Chains** -- Configure fallback providers for high availability
- **Response Caching** -- Cache AI responses to reduce costs

## Cost Tracking

AI costs are automatically tracked and included in the response envelope:

```json
{
  "ai": {
    "model": "gpt-4",
    "provider": "openai",
    "tokens": 150,
    "cost": 0.003,
    "cached": false,
    "response_time_ms": 850
  }
}
```

## CLI Commands

```bash
vorte ai:models           # List models with pricing
vorte ai:costs            # Show cost report
vorte ai:costs --period today
```
