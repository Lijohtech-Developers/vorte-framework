# Agents Module

Build AI agents with tools, memory, RAG pipelines, and guardrails.

## Setup

```python
from vorte import AgentsModule

app.register(AgentsModule())
```

## Core Components

### Agents

AI agents with tool use capabilities:

```python
# Generate an agent scaffold
# vorte make:agent support_bot
```

Agents support:
- Tool calling (function execution)
- Multi-step reasoning
- Conversation memory
- RAG integration

### Tools

Define tools that agents can invoke:

```python
from vorte.modules.agents import Tool

def search_knowledge_base(query: str) -> dict:
    """Search the knowledge base for relevant information."""
    return {"results": [...]}

tool = Tool(
    name="search",
    description="Search the knowledge base",
    function=search_knowledge_base,
)
```

### Memory

Conversation memory with short-term and long-term storage:

```python
from vorte.modules.agents.memory import ConversationMemory, MemoryConfig

memory = ConversationMemory(
    config=MemoryConfig(
        max_turns=20,
        max_tokens=4000,
        enable_long_term=True,
        summarization_interval=10,
    )
)

# Add messages
memory.add("user", "What is Vorte?")
memory.add("assistant", "Vorte is an AI-first framework...")

# Keyword search
results = memory.search("framework")

# Export/import
data = memory.export()
memory.import_data(data)
```

Memory automatically trims when `max_turns` or `max_tokens` limits are reached.

### RAG (Retrieval-Augmented Generation)

RAG pipelines for context-aware AI responses:

```python
# Built-in RAG pipeline for document retrieval + generation
# Integrates with the Search module for vector search
```

### Pipelines

Multi-step AI pipelines with configurable nodes:

```bash
vorte make:pipeline content_pipeline
```

Pipelines allow chaining multiple AI operations:
1. Input processing
2. Context retrieval (RAG)
3. Generation
4. Post-processing / guardrails

### Guardrails

Safety guardrails for AI output validation:
- Content filtering
- Output format validation
- Toxicity detection
- Custom validation rules

### Prompts

Versioned prompt templates with variable interpolation:

```python
from vorte.modules.agents.prompts import PromptRegistry

registry = PromptRegistry()

# Register a template with {{variable}} placeholders
registry.register(
    name="greeting",
    template="Hello {{name}}! Welcome to {{app}}.",
    version="1.0.0",
)

# Render with variables
text = registry.render("greeting", name="Alice", app="Vorte")
# "Hello Alice! Welcome to Vorte."

# Activate/deactivate versions
registry.activate("greeting", "1.0.0")
```

## Agent Orchestration

The module includes an orchestrator that:
- Manages agent lifecycle
- Handles tool dispatch
- Coordinates multi-agent workflows
- Tracks token usage and costs
