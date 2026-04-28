"""
Multi-Agent Orchestrator
=========================
Orchestrates multiple agents to work together on complex tasks. Supports
sequential task delegation, parallel execution of sub-agents, and result
aggregation.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from vorte.modules.agents.agent import Agent, AgentConfig, AgentResponse, AgentRole


class ExecutionStrategy(str, Enum):
    """Strategy for executing sub-agents."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    ROUND_ROBIN = "round_robin"
    DYNAMIC = "dynamic"


class AggregationStrategy(str, Enum):
    """Strategy for aggregating results from multiple agents."""
    FIRST = "first"
    CONCAT = "concat"
    SUMMARY = "summary"
    VOTE = "vote"
    CUSTOM = "custom"


@dataclass
class OrchestratorConfig:
    """
    Configuration for the multi-agent orchestrator.

    Attributes:
        max_parallel: Maximum number of agents to run in parallel.
        execution_strategy: How to execute sub-agents (sequential, parallel, etc.).
        aggregation_strategy: How to combine results from multiple agents.
        timeout: Maximum time in seconds for the full orchestration.
        retry_on_failure: Whether to retry failed agent runs.
        max_retries: Maximum number of retries per agent.
        verbose: Whether to log detailed execution information.
    """
    max_parallel: int = 5
    execution_strategy: ExecutionStrategy = ExecutionStrategy.DYNAMIC
    aggregation_strategy: AggregationStrategy = AggregationStrategy.FIRST
    timeout: float = 300.0
    retry_on_failure: bool = True
    max_retries: int = 2
    verbose: bool = False


@dataclass
class DelegationResult:
    """
    Result from delegating a task to a sub-agent.

    Attributes:
        agent_name: Name of the agent that executed the task.
        task: The task that was delegated.
        response: The AgentResponse from the sub-agent.
        success: Whether the delegation succeeded.
        error: Error message if the delegation failed.
        duration_ms: Time taken for the delegation.
    """
    agent_name: str
    task: str
    response: Optional[AgentResponse] = None
    success: bool = True
    error: Optional[str] = None
    duration_ms: float = 0.0

    @property
    def content(self) -> str:
        """Get the response content."""
        return self.response.content if self.response else ""


@dataclass
class OrchestrationResult:
    """
    Result from a full orchestration run.

    Attributes:
        content: The final aggregated content.
        delegations: List of individual DelegationResult entries.
        total_tokens: Total tokens used across all agents.
        duration_ms: Total orchestration time in milliseconds.
        success: Whether the overall orchestration succeeded.
        error: Error message if the orchestration failed.
        metadata: Additional metadata.
    """
    content: str
    delegations: List[DelegationResult] = field(default_factory=list)
    total_tokens: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def successful_delegations(self) -> List[DelegationResult]:
        """Get only successful delegation results."""
        return [d for d in self.delegations if d.success]

    @property
    def failed_delegations(self) -> List[DelegationResult]:
        """Get only failed delegation results."""
        return [d for d in self.delegations if not d.success]


class AgentOrchestrator:
    """
    Multi-agent orchestrator for coordinating complex tasks.

    Manages a team of sub-agents and delegates tasks to them using
    configurable execution and aggregation strategies.

    Usage:
        orchestrator = AgentOrchestrator(
            sub_agents=[researcher, writer, reviewer],
            execution_strategy=ExecutionStrategy.SEQUENTIAL,
        )
        result = await orchestrator.run("Write a research report on AI")

        # With parallel execution
        orchestrator = AgentOrchestrator(
            sub_agents=[translator_en, translator_fr, translator_sw],
            execution_strategy=ExecutionStrategy.PARALLEL,
        )
        result = await orchestrator.run("Translate: Hello world")
    """

    def __init__(
        self,
        *,
        sub_agents: Optional[Sequence[Agent]] = None,
        config: Optional[OrchestratorConfig] = None,
        name: str = "orchestrator",
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        aggregation_fn: Optional[Callable[[List[DelegationResult]], str]] = None,
    ) -> None:
        self._config = config or OrchestratorConfig()
        self._sub_agents: Dict[str, Agent] = {}
        self._name = name
        self._system_prompt = system_prompt or (
            "You are an orchestrator that delegates tasks to specialized agents "
            "and combines their results."
        )
        self._model = model or "gpt-4o"
        self._aggregation_fn = aggregation_fn
        self._execution_log: List[Dict[str, Any]] = []

        if sub_agents:
            for agent in sub_agents:
                self._sub_agents[agent.name] = agent

    @property
    def config(self) -> OrchestratorConfig:
        """Get the orchestrator configuration."""
        return self._config

    @property
    def sub_agents(self) -> Dict[str, Agent]:
        """Get registered sub-agents."""
        return dict(self._sub_agents)

    @property
    def execution_log(self) -> List[Dict[str, Any]]:
        """Get the execution log."""
        return list(self._execution_log)

    # ---- Agent Management ----

    def add_agent(self, agent: Agent) -> AgentOrchestrator:
        """
        Register a sub-agent.

        Args:
            agent: The Agent to register.

        Returns:
            self for chaining.
        """
        self._sub_agents[agent.name] = agent
        return self

    def remove_agent(self, name: str) -> AgentOrchestrator:
        """
        Remove a registered sub-agent.

        Args:
            name: The agent name to remove.

        Returns:
            self for chaining.
        """
        self._sub_agents.pop(name, None)
        return self

    # ---- Core Execution ----

    async def run(
        self,
        task: str,
        *,
        strategy: Optional[ExecutionStrategy] = None,
        agent_names: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> OrchestrationResult:
        """
        Run the orchestration for a given task.

        Delegates the task to sub-agents using the configured or specified
        execution strategy, then aggregates the results.

        Args:
            task: The task description to orchestrate.
            strategy: Override execution strategy for this run.
            agent_names: Specific agents to use (None = all).
            context: Additional context for the orchestration.

        Returns:
            An OrchestrationResult with the aggregated output.
        """
        start_time = time.time()
        self._execution_log.clear()

        exec_strategy = strategy or self._config.execution_strategy
        target_agents = self._get_target_agents(agent_names)

        if not target_agents:
            return OrchestrationResult(
                content="No agents available for delegation.",
                success=False,
                error="No sub-agents registered.",
                duration_ms=(time.time() - start_time) * 1000,
            )

        try:
            if exec_strategy == ExecutionStrategy.SEQUENTIAL:
                delegations = await self._run_sequential(task, target_agents)
            elif exec_strategy == ExecutionStrategy.PARALLEL:
                delegations = await self._run_parallel(task, target_agents)
            elif exec_strategy == ExecutionStrategy.ROUND_ROBIN:
                delegations = await self._run_round_robin(task, target_agents)
            elif exec_strategy == ExecutionStrategy.DYNAMIC:
                delegations = await self._run_dynamic(task, target_agents, context)
            else:
                delegations = await self._run_sequential(task, target_agents)

            # Aggregate results
            content = self._aggregate(delegations)
            total_tokens = sum(
                d.response.total_tokens
                for d in delegations
                if d.response
            )

            duration_ms = (time.time() - start_time) * 1000

            return OrchestrationResult(
                content=content,
                delegations=delegations,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
                success=True,
                metadata={"strategy": exec_strategy.value, "task": task},
            )

        except asyncio.TimeoutError:
            duration_ms = (time.time() - start_time) * 1000
            return OrchestrationResult(
                content="",
                duration_ms=duration_ms,
                success=False,
                error="Orchestration timed out.",
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return OrchestrationResult(
                content="",
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )

    async def delegate_to(
        self,
        agent_name: str,
        task: str,
    ) -> DelegationResult:
        """
        Delegate a task to a specific sub-agent.

        Args:
            agent_name: The name of the sub-agent.
            task: The task to delegate.

        Returns:
            A DelegationResult with the agent's response.
        """
        agent = self._sub_agents.get(agent_name)
        if not agent:
            return DelegationResult(
                agent_name=agent_name,
                task=task,
                success=False,
                error=f"Agent '{agent_name}' not found.",
            )

        start_time = time.time()

        try:
            response = await agent.run(task)
            duration_ms = (time.time() - start_time) * 1000

            return DelegationResult(
                agent_name=agent_name,
                task=task,
                response=response,
                success=response.success,
                error=response.error,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return DelegationResult(
                agent_name=agent_name,
                task=task,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

    # ---- Execution Strategies ----

    async def _run_sequential(
        self,
        task: str,
        agents: List[Tuple[str, Agent]],
    ) -> List[DelegationResult]:
        """Execute agents one after another, passing context forward."""
        delegations: List[DelegationResult] = []
        context = task

        for name, agent in agents:
            result = await self._execute_with_retry(name, agent, context)
            delegations.append(result)

            self._log_execution(name, task, result)

            if result.success and result.content:
                context = f"Original task: {task}\nPrevious agent '{name}' result: {result.content}\nContinue the task."

        return delegations

    async def _run_parallel(
        self,
        task: str,
        agents: List[Tuple[str, Agent]],
    ) -> List[DelegationResult]:
        """Execute all agents in parallel."""
        semaphore = asyncio.Semaphore(self._config.max_parallel)

        async def _bounded_execute(name: str, agent: Agent) -> DelegationResult:
            async with semaphore:
                return await self._execute_with_retry(name, agent, task)

        tasks = [
            _bounded_execute(name, agent)
            for name, agent in agents
        ]

        delegations = await asyncio.gather(*tasks)

        for result in delegations:
            self._log_execution(result.agent_name, task, result)

        return list(delegations)

    async def _run_round_robin(
        self,
        task: str,
        agents: List[Tuple[str, Agent]],
    ) -> List[DelegationResult]:
        """Delegate to agents in rotation."""
        delegations: List[DelegationResult] = []
        parts = self._split_task(task, len(agents))

        for i, (name, agent) in enumerate(agents):
            sub_task = parts[i] if i < len(parts) else task
            result = await self._execute_with_retry(name, agent, sub_task)
            delegations.append(result)
            self._log_execution(name, sub_task, result)

        return delegations

    async def _run_dynamic(
        self,
        task: str,
        agents: List[Tuple[str, Agent]],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[DelegationResult]:
        """
        Dynamically decide which agents to use based on the task.

        Uses the orchestrator's model to analyze the task and select
        the most appropriate agents.
        """
        delegations: List[DelegationResult] = []

        # Analyze task and select agents
        selected_agents = await self._select_agents(task, agents)

        if not selected_agents:
            # Fall back to sequential if no agents selected
            selected_agents = agents

        for name, agent in selected_agents:
            result = await self._execute_with_retry(name, agent, task)
            delegations.append(result)
            self._log_execution(name, task, result)

        return delegations

    # ---- Helper Methods ----

    async def _select_agents(
        self,
        task: str,
        available_agents: List[Tuple[str, Agent]],
    ) -> List[Tuple[str, Agent]]:
        """
        Select appropriate agents for a task.

        In production, this would use the LLM to analyze the task and select
        agents. For now, returns all agents.
        """
        # Placeholder: in production, use the LLM to analyze the task
        # and select the most appropriate agents based on their roles
        # and system prompts
        return available_agents

    async def _execute_with_retry(
        self,
        name: str,
        agent: Agent,
        task: str,
    ) -> DelegationResult:
        """Execute a delegation with retry logic."""
        result = await self.delegate_to(name, task)

        if not result.success and self._config.retry_on_failure:
            for attempt in range(self._config.max_retries):
                result = await self.delegate_to(name, task)
                if result.success:
                    break

        return result

    def _aggregate(self, delegations: List[DelegationResult]) -> str:
        """Aggregate results from delegations."""
        if not delegations:
            return ""

        # Custom aggregation function takes priority
        if self._aggregation_fn:
            return self._aggregation_fn(delegations)

        strategy = self._config.aggregation_strategy

        if strategy == AggregationStrategy.FIRST:
            for d in delegations:
                if d.success and d.content:
                    return d.content
            return ""

        elif strategy == AggregationStrategy.CONCAT:
            parts = []
            for d in delegations:
                if d.success and d.content:
                    parts.append(f"[{d.agent_name}]: {d.content}")
            return "\n\n".join(parts) if parts else ""

        elif strategy == AggregationStrategy.SUMMARY:
            contents = [d.content for d in delegations if d.success and d.content]
            if not contents:
                return ""
            if len(contents) == 1:
                return contents[0]
            return f"[Summary of {len(contents)} agent responses]\n" + "\n".join(
                f"- {c}" for c in contents
            )

        elif strategy == AggregationStrategy.VOTE:
            # Return the most common non-empty response
            from collections import Counter
            contents = [d.content for d in delegations if d.success and d.content]
            if not contents:
                return ""
            counter = Counter(contents)
            return counter.most_common(1)[0][0]

        elif strategy == AggregationStrategy.CUSTOM:
            # This should not be reached if _aggregation_fn is set
            return ""

        return ""

    def _get_target_agents(
        self,
        agent_names: Optional[List[str]] = None,
    ) -> List[Tuple[str, Agent]]:
        """Get the target agents for a run."""
        if agent_names:
            return [
                (name, self._sub_agents[name])
                for name in agent_names
                if name in self._sub_agents
            ]
        return list(self._sub_agents.items())

    def _split_task(
        self,
        task: str,
        num_parts: int,
    ) -> List[str]:
        """Split a task into roughly equal parts for round-robin."""
        if num_parts <= 1:
            return [task]

        words = task.split()
        part_size = max(1, len(words) // num_parts)
        parts = []

        for i in range(num_parts):
            start = i * part_size
            end = start + part_size if i < num_parts - 1 else len(words)
            part = " ".join(words[start:end])
            if part:
                parts.append(part)

        return parts if parts else [task]

    def _log_execution(
        self,
        agent_name: str,
        task: str,
        result: DelegationResult,
    ) -> None:
        """Log an execution for debugging."""
        if self._config.verbose:
            self._execution_log.append({
                "agent": agent_name,
                "task": task,
                "success": result.success,
                "duration_ms": result.duration_ms,
                "error": result.error,
            })

    def clear(self) -> None:
        """Clear the execution log."""
        self._execution_log.clear()

    def __repr__(self) -> str:
        return (
            f"AgentOrchestrator(name={self._name!r}, "
            f"agents={list(self._sub_agents.keys())}, "
            f"strategy={self._config.execution_strategy.value})"
        )
