"""
Base Agent Class
================
Core Agent class providing model configuration, system prompts, tool integration,
memory management, and multi-agent delegation support.
"""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from vorte.modules.agents.memory import ConversationMemory, MemoryConfig
from vorte.modules.agents.tools import Tool, ToolRegistry


class AgentRole(str, Enum):
    """Preset agent roles with sensible defaults."""
    ASSISTANT = "assistant"
    CODER = "coder"
    ANALYST = "analyst"
    WRITER = "writer"
    REVIEWER = "reviewer"
    ORCHESTRATOR = "orchestrator"
    RAG = "rag"
    CUSTOM = "custom"


@dataclass
class AgentConfig:
    """Configuration for an Agent instance."""
    name: str = "agent"
    model: str = "gpt-4o"
    system_prompt: str = "You are a helpful AI assistant."
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    stop_sequences: Optional[List[str]] = None
    tools: Optional[List[Tool]] = None
    memory_config: Optional[MemoryConfig] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    role: AgentRole = AgentRole.CUSTOM
    max_delegations: int = 10
    timeout: float = 120.0


@dataclass
class AgentResponse:
    """Response from an Agent run."""
    content: str
    agent_name: str
    model: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    tokens_used: Dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        """Total tokens used in this response."""
        return sum(self.tokens_used.values())


class Agent:
    """
    Base Agent class.

    Provides a configurable AI agent with model integration, tool support,
    conversation memory, and multi-agent delegation capabilities.

    Usage:
        agent = Agent(
            name="assistant",
            model="gpt-4o",
            system_prompt="You are a helpful assistant.",
        )
        response = await agent.run("Hello, how are you?")

        # With tools
        agent = Agent(
            name="coder",
            model="gpt-4o",
            system_prompt="You are a coding assistant.",
            tools=[search_tool, calculate_tool],
        )
        response = await agent.run("What is 42 * 17?")
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[Sequence[Union[Tool, Callable]]] = None,
        memory_config: Optional[MemoryConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
        role: AgentRole = AgentRole.CUSTOM,
        max_delegations: int = 10,
        timeout: float = 120.0,
        config: Optional[AgentConfig] = None,
    ) -> None:
        if config:
            self._config = config
        else:
            self._config = AgentConfig(
                name=name or "agent",
                model=model or "gpt-4o",
                system_prompt=system_prompt or "You are a helpful AI assistant.",
                temperature=temperature if temperature is not None else 0.7,
                max_tokens=max_tokens or 4096,
                top_p=top_p if top_p is not None else 1.0,
                stop_sequences=stop_sequences,
                memory_config=memory_config or MemoryConfig(),
                metadata=metadata or {},
                role=role,
                max_delegations=max_delegations,
                timeout=timeout,
            )

        self._tool_registry = ToolRegistry()
        self._memory = ConversationMemory(self._config.memory_config)
        self._delegation_count = 0
        self._sub_agents: Dict[str, "Agent"] = {}
        self._hooks: Dict[str, List[Callable]] = {
            "pre_run": [],
            "post_run": [],
            "pre_tool_call": [],
            "post_tool_call": [],
            "on_error": [],
        }

        # Register tools if provided
        if self._config.tools:
            for t in self._config.tools:
                self._tool_registry.register(t)

        # Register additional tools passed via constructor
        if tools:
            for t in tools:
                if isinstance(t, Tool):
                    self._tool_registry.register(t)
                elif callable(t):
                    self._tool_registry.register_from_callable(t)

    # ---- Properties ----

    @property
    def config(self) -> AgentConfig:
        """Get the agent configuration."""
        return self._config

    @property
    def name(self) -> str:
        """Get the agent name."""
        return self._config.name

    @property
    def model(self) -> str:
        """Get the model name."""
        return self._config.model

    @property
    def memory(self) -> ConversationMemory:
        """Get the conversation memory."""
        return self._memory

    @property
    def tool_registry(self) -> ToolRegistry:
        """Get the tool registry."""
        return self._tool_registry

    @property
    def tools(self) -> List[Tool]:
        """Get all registered tools."""
        return self._tool_registry.list_tools()

    @property
    def sub_agents(self) -> Dict[str, Agent]:
        """Get registered sub-agents."""
        return dict(self._sub_agents)

    # ---- Tool Registration ----

    def add_tool(self, tool: Union[Tool, Callable]) -> "Agent":
        """
        Add a tool to the agent.

        Args:
            tool: A Tool instance or a callable function.

        Returns:
            self for chaining.
        """
        if isinstance(tool, Tool):
            self._tool_registry.register(tool)
        elif callable(tool):
            self._tool_registry.register_from_callable(tool)
        return self

    def add_tools(self, tools: Sequence[Union[Tool, Callable]]) -> "Agent":
        """
        Add multiple tools to the agent.

        Args:
            tools: A sequence of Tool instances or callables.

        Returns:
            self for chaining.
        """
        for t in tools:
            self.add_tool(t)
        return self

    # ---- Sub-Agent Registration ----

    def add_sub_agent(self, agent: "Agent") -> "Agent":
        """
        Register a sub-agent for delegation.

        Args:
            agent: An Agent instance to register as a sub-agent.

        Returns:
            self for chaining.
        """
        self._sub_agents[agent.name] = agent
        return self

    # ---- Hooks ----

    def on(self, event: str) -> Callable:
        """
        Register a lifecycle hook.

        Args:
            event: One of 'pre_run', 'post_run', 'pre_tool_call',
                   'post_tool_call', 'on_error'.

        Returns:
            Decorator function.
        """
        def decorator(func: Callable) -> Callable:
            if event in self._hooks:
                self._hooks[event].append(func)
            return func
        return decorator

    async def _run_hooks(self, event: str, **kwargs: Any) -> None:
        """Run all hooks for a given event."""
        for hook in self._hooks.get(event, []):
            result = hook(**kwargs)
            if asyncio.iscoroutine(result):
                await result

    # ---- Core Run Method ----

    async def run(
        self,
        message: str,
        *,
        tools_enabled: bool = True,
        memory_enabled: bool = True,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Run the agent with a message.

        Processes the message through guardrails, builds the conversation
        context from memory, executes the model call (with tool use if
        enabled), and returns a structured AgentResponse.

        Args:
            message: The user message to process.
            tools_enabled: Whether to allow tool calls.
            memory_enabled: Whether to use conversation memory.
            **kwargs: Additional overrides passed to the completion API.

        Returns:
            An AgentResponse with the result.
        """
        start_time = time.time()
        self._delegation_count = 0

        try:
            # Pre-run hook
            await self._run_hooks("pre_run", message=message)

            # Build messages context
            messages = self._build_messages(message, memory_enabled)

            # Prepare tool schemas if tools are enabled
            tool_schemas: Optional[List[Dict[str, Any]]] = None
            if tools_enabled and self._tool_registry.has_tools():
                tool_schemas = self._tool_registry.get_openai_schemas()

            # Execute completion
            completion_result = await self._execute_completion(
                messages=messages,
                tools=tool_schemas,
                **kwargs,
            )

            # Handle tool calls if present
            tool_calls: List[Dict[str, Any]] = []
            tool_results: List[Dict[str, Any]] = []

            if completion_result.get("tool_calls") and tools_enabled:
                tool_calls = completion_result["tool_calls"]
                tool_results = await self._execute_tool_calls(tool_calls, messages)
                # If tool calls were made, re-run to get final response
                if tool_results:
                    completion_result = await self._execute_completion(
                        messages=messages + tool_results,
                        tools=tool_schemas,
                        **kwargs,
                    )

            content = completion_result.get("content", "")
            tokens_used = completion_result.get("tokens_used", {})

            # Add to memory
            if memory_enabled:
                self._memory.add_user(message)
                self._memory.add_assistant(content)

            # Post-run hook
            await self._run_hooks(
                "post_run",
                message=message,
                response=content,
            )

            duration_ms = (time.time() - start_time) * 1000

            return AgentResponse(
                content=content,
                agent_name=self._config.name,
                model=self._config.model,
                tool_calls=tool_calls,
                tool_results=tool_results,
                tokens_used=tokens_used,
                duration_ms=duration_ms,
                metadata=self._config.metadata,
                success=True,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # Error hook
            await self._run_hooks("on_error", error=e, message=message)

            return AgentResponse(
                content="",
                agent_name=self._config.name,
                model=self._config.model,
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )

    # ---- Delegation ----

    async def delegate(self, sub_agent: "Agent", task: str) -> AgentResponse:
        """
        Delegate a task to a sub-agent.

        Args:
            sub_agent: The Agent to delegate to.
            task: The task description/message.

        Returns:
            An AgentResponse from the sub-agent.

        Raises:
            RuntimeError: If the delegation limit is exceeded.
        """
        self._delegation_count += 1
        if self._delegation_count > self._config.max_delegations:
            raise RuntimeError(
                f"Agent '{self._config.name}' exceeded maximum "
                f"delegations ({self._config.max_delegations})."
            )

        return await sub_agent.run(task)

    # ---- Internal Methods ----

    def _build_messages(
        self,
        message: str,
        memory_enabled: bool,
    ) -> List[Dict[str, str]]:
        """
        Build the messages list for the completion API.

        Includes the system prompt and conversation history from memory.
        """
        messages: List[Dict[str, str]] = []

        # System prompt
        if self._config.system_prompt:
            messages.append({
                "role": "system",
                "content": self._config.system_prompt,
            })

        # Conversation history from memory
        if memory_enabled:
            for entry in self._memory.get_recent():
                messages.append({
                    "role": entry.role,
                    "content": entry.content,
                })

        # Current user message
        messages.append({
            "role": "user",
            "content": message,
        })

        return messages

    async def _execute_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute the AI completion call.

        Integrates with the Vorte AI module's completion API when available,
        otherwise provides a stub response for standalone usage.

        Args:
            messages: The message list.
            tools: Optional tool schemas for function calling.
            **kwargs: Additional parameters.

        Returns:
            A dict with 'content', 'tool_calls', and 'tokens_used'.
        """
        try:
            from vorte.core.di import _global_container

            # Try to get the AI module completion function
            ai_module = None
            if hasattr(_global_container, "_instances"):
                for iface, inst in _global_container._instances.items():
                    if hasattr(inst, "meta") and inst.meta.name == "ai":
                        ai_module = inst
                        break

            if ai_module and hasattr(ai_module, "completion"):
                return await ai_module.completion(
                    model=self._config.model,
                    messages=messages,
                    tools=tools,
                    temperature=kwargs.get("temperature", self._config.temperature),
                    max_tokens=kwargs.get("max_tokens", self._config.max_tokens),
                    top_p=kwargs.get("top_p", self._config.top_p),
                    stop=kwargs.get("stop", self._config.stop_sequences),
                )
        except (ImportError, AttributeError):
            pass

        # Fallback: return a placeholder response
        # In production, this would call an actual LLM provider
        return {
            "content": f"[Agent '{self._config.name}' response placeholder - connect AI module for real completions]",
            "tool_calls": [],
            "tokens_used": {"prompt": 0, "completion": 0, "total": 0},
        }

    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """
        Execute a list of tool calls and return their results.

        Args:
            tool_calls: List of tool call dicts from the model.
            messages: The current messages list (for context).

        Returns:
            List of tool result dicts suitable for appending to messages.
        """
        results: List[Dict[str, Any]] = []

        for call in tool_calls:
            tool_name = call.get("name", call.get("function", {}).get("name", ""))
            arguments = call.get("arguments", call.get("function", {}).get("arguments", {}))

            if isinstance(arguments, str):
                import json
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            await self._run_hooks(
                "pre_tool_call",
                tool_name=tool_name,
                arguments=arguments,
            )

            try:
                result = await self._tool_registry.execute(
                    tool_name,
                    **arguments,
                )
                result_str = str(result)
            except Exception as e:
                result_str = f"Error executing tool '{tool_name}': {e}"

            await self._run_hooks(
                "post_tool_call",
                tool_name=tool_name,
                result=result_str,
            )

            # Format as tool result message
            call_id = call.get("id", str(uuid.uuid4()))
            results.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": result_str,
            })

        return results

    # ---- Convenience Methods ----

    def clear_memory(self) -> None:
        """Clear the agent's conversation memory."""
        self._memory.clear()

    def reset(self) -> None:
        """Reset the agent to initial state."""
        self._memory.clear()
        self._delegation_count = 0

    def __repr__(self) -> str:
        return (
            f"Agent(name={self._config.name!r}, model={self._config.model!r}, "
            f"tools={len(self._tool_registry)}, role={self._config.role.value})"
        )
