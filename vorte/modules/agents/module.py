"""
Agents Module
=============
Vorte module that provides AI agent framework, multi-agent orchestration,
RAG pipelines, and AI guardrails.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from vorte.core.module import Module, ModuleMeta, ModulePriority, ModuleState
from vorte.core.di import Container, Depends

if TYPE_CHECKING:
    from vorte.core.app import Vorte


class AgentsModule(Module):
    """
    AI Agents & Pipelines module.

    Provides a complete agent framework including:
    - Base Agent class with tool support
    - Tool system with auto-schema generation
    - Conversation memory (short-term & long-term)
    - Multi-agent orchestration with parallel execution
    - RAG (Retrieval Augmented Generation) agents
    - AI Pipeline system for chained processing
    - AI Guardrails (PII, content safety, language, token budget)
    - Prompt versioning and registry

    Usage:
        app = Vorte()
        app.register(AgentsModule(
            default_model="gpt-4o",
            max_tokens=4096,
        ))
    """

    meta = ModuleMeta(
        name="agents",
        version="1.0.0",
        description="AI agent framework with orchestration, RAG, pipelines, and guardrails",
        priority=ModulePriority.AI,
        dependencies=["ai"],
    )

    def __init__(
        self,
        *,
        default_model: str = "gpt-4o",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        enable_guardrails: bool = True,
        enable_rag: bool = True,
        enable_pipelines: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._default_model = default_model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._enable_guardrails = enable_guardrails
        self._enable_rag = enable_rag
        self._enable_pipelines = enable_pipelines

        # Registries
        self._agent_registry: Dict[str, Any] = {}
        self._tool_registry: Optional[Any] = None
        self._prompt_registry: Optional[Any] = None
        self._guardrails: List[Any] = []

    def register(self, app: "Vorte") -> None:
        """
        Register the agents module with the Vorte application.

        Sets up the tool registry, prompt registry, and default guardrails.
        Registers the module's services in the DI container.
        """
        from vorte.modules.agents.tools import ToolRegistry
        from vorte.modules.agents.prompts import PromptRegistry
        from vorte.modules.agents.guardrails import (
            NoPIIGuardrail,
            NoHarmfulContentGuardrail,
        )

        # Initialize registries
        self._tool_registry = ToolRegistry()
        self._prompt_registry = PromptRegistry()

        # Register in DI container
        app.container.register_instance(ToolRegistry, self._tool_registry)
        app.container.register_instance(PromptRegistry, self._prompt_registry)

        # Setup default guardrails if enabled
        if self._enable_guardrails:
            self._guardrails = [
                NoPIIGuardrail(),
                NoHarmfulContentGuardrail(),
            ]

        self.state = ModuleState.READY

    async def on_startup(self) -> None:
        """Called when the application starts."""
        pass

    async def on_shutdown(self) -> None:
        """Called when the application shuts down."""
        # Clear registries
        self._agent_registry.clear()
        if self._tool_registry:
            self._tool_registry.clear()
        self._guardrails.clear()

    def register_agent(self, name: str, agent: Any) -> None:
        """
        Register a named agent in the module registry.

        Args:
            name: Unique name for the agent.
            agent: An Agent instance to register.
        """
        self._agent_registry[name] = agent

    def get_agent(self, name: str) -> Optional[Any]:
        """
        Retrieve a registered agent by name.

        Args:
            name: The agent name.

        Returns:
            The Agent instance or None if not found.
        """
        return self._agent_registry.get(name)

    def list_agents(self) -> List[str]:
        """List all registered agent names."""
        return list(self._agent_registry.keys())

    def add_guardrail(self, guardrail: Any) -> None:
        """
        Add a guardrail to the module-level guardrails list.

        Args:
            guardrail: A Guardrail instance.
        """
        self._guardrails.append(guardrail)

    def remove_guardrail(self, guardrail_type: type) -> None:
        """
        Remove a guardrail by type.

        Args:
            guardrail_type: The type of guardrail to remove.
        """
        self._guardrails = [
            g for g in self._guardrails if not isinstance(g, guardrail_type)
        ]

    @property
    def tool_registry(self) -> Optional[Any]:
        """Get the tool registry."""
        return self._tool_registry

    @property
    def prompt_registry(self) -> Optional[Any]:
        """Get the prompt registry."""
        return self._prompt_registry

    @property
    def guardrails(self) -> List[Any]:
        """Get the list of active guardrails."""
        return list(self._guardrails)

    @property
    def default_model(self) -> str:
        """Get the default model name."""
        return self._default_model

    @property
    def max_tokens(self) -> int:
        """Get the max tokens setting."""
        return self._max_tokens

    async def health_check(self) -> Dict[str, Any]:
        """Check if the agents module is healthy."""
        base = await super().health_check()
        base.update({
            "agents_registered": len(self._agent_registry),
            "tools_registered": len(self._tool_registry._tools) if self._tool_registry else 0,
            "guardrails_active": len(self._guardrails),
            "default_model": self._default_model,
        })
        return base

