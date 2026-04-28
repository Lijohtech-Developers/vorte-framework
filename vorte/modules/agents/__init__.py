"""
Vorte AI Agents & Pipelines Module
=====================================
Provides agent framework, multi-agent orchestration, RAG, and AI guardrails.

Usage:
    from vorte.modules.agents import AgentsModule, Agent, AIPipeline

    # Register the module
    app.register(AgentsModule())

    # Create an agent
    agent = Agent(
        name="assistant",
        model="gpt-4o",
        system_prompt="You are a helpful assistant.",
    )
    result = await agent.run("Hello!")

    # Build a pipeline with guardrails
    pipeline = AIPipeline(steps=[
        NoPIIGuardrail(),
        agent,
        TokenBudgetGuardrail(max_tokens=1000),
    ])
    result = await pipeline.run("Tell me about X...")
"""

from vorte.modules.agents.module import AgentsModule
from vorte.modules.agents.agent import Agent, AgentConfig, AgentResponse
from vorte.modules.agents.tools import Tool, ToolRegistry, tool
from vorte.modules.agents.memory import (
    MemoryEntry,
    ConversationMemory,
    MemoryConfig,
)
from vorte.modules.agents.orchestrator import (
    AgentOrchestrator,
    OrchestratorConfig,
    DelegationResult,
)
from vorte.modules.agents.rag import RAGAgent, RAGConfig, VectorStoreConfig
from vorte.modules.agents.pipeline import (
    AIPipeline,
    PipelineStep,
    PipelineResult,
)
from vorte.modules.agents.guardrails import (
    Guardrail,
    GuardrailResult,
    NoPIIGuardrail,
    NoHarmfulContentGuardrail,
    LanguageGuardrail,
    TokenBudgetGuardrail,
)
from vorte.modules.agents.prompts import (
    PromptVersion,
    PromptRegistry,
)

__all__ = [
    # Module
    "AgentsModule",
    # Agent
    "Agent",
    "AgentConfig",
    "AgentResponse",
    # Tools
    "Tool",
    "ToolRegistry",
    "tool",
    # Memory
    "MemoryEntry",
    "ConversationMemory",
    "MemoryConfig",
    # Orchestrator
    "AgentOrchestrator",
    "OrchestratorConfig",
    "DelegationResult",
    # RAG
    "RAGAgent",
    "RAGConfig",
    "VectorStoreConfig",
    # Pipeline
    "AIPipeline",
    "PipelineStep",
    "PipelineResult",
    # Guardrails
    "Guardrail",
    "GuardrailResult",
    "NoPIIGuardrail",
    "NoHarmfulContentGuardrail",
    "LanguageGuardrail",
    "TokenBudgetGuardrail",
    # Prompts
    "PromptVersion",
    "PromptRegistry",
]
