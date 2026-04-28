"""
AI Pipeline System
==================
Provides a composable pipeline system for chaining AI processing steps.
Each step processes input data and passes its output to the next step,
enabling guardrails, transformations, agent calls, and post-processing
to be composed into reusable workflows.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")


@dataclass
class PipelineResult:
    """
    Result from running an AI pipeline.

    Attributes:
        output: The final output from the pipeline.
        step_results: Individual results from each pipeline step.
        total_tokens: Total tokens used across all steps.
        duration_ms: Total pipeline execution time in milliseconds.
        success: Whether the pipeline completed successfully.
        error: Error message if the pipeline failed.
        metadata: Additional metadata from the pipeline run.
        stopped_at: Index of the step that stopped the pipeline (e.g., guardrail
            rejection), or None if the pipeline ran to completion.
    """
    output: Any = None
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    stopped_at: Optional[int] = None


class PipelineStep(ABC):
    """
    Abstract base class for a pipeline step.

    Each step receives input data, processes it, and returns output data.
    Steps can be agents, guardrails, transformers, or any other processor.

    Usage:
        class UpperCaseStep(PipelineStep):
            async def process(self, input_data):
                return input_data.upper()

        class GuardStep(PipelineStep):
            async def process(self, input_data):
                if "bad" in input_data:
                    raise PipelineStop("Content rejected")
                return input_data
    """

    @property
    def name(self) -> str:
        """Get the step name. Defaults to class name."""
        return self.__class__.__name__

    @abstractmethod
    async def process(self, input_data: Any, **kwargs: Any) -> Any:
        """
        Process the input data and return output.

        Args:
            input_data: The data to process.
            **kwargs: Additional context or configuration.

        Returns:
            The processed output to pass to the next step.
        """
        ...

    def __repr__(self) -> str:
        return f"PipelineStep(name={self.name!r})"


class PipelineStop(Exception):
    """
    Exception to signal that a pipeline should stop processing.

    Raised by a pipeline step (e.g., a guardrail) to halt the pipeline
    and return early.

    Attributes:
        message: Reason for stopping.
        modified_data: Optionally modified data to return.
    """

    def __init__(
        self,
        message: str = "Pipeline stopped",
        modified_data: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.modified_data = modified_data


class FunctionStep(PipelineStep):
    """
    A pipeline step that wraps a callable function.

    Supports both sync and async functions.

    Usage:
        step = FunctionStep(lambda x: x.upper(), name="uppercase")
        step = FunctionStep(my_async_function, name="process")
    """

    def __init__(
        self,
        func: Callable,
        *,
        name: Optional[str] = None,
        description: str = "",
    ) -> None:
        self._func = func
        self._step_name = name or func.__name__
        self._description = description
        self._is_async = asyncio.iscoroutinefunction(func)

    @property
    def name(self) -> str:
        return self._step_name

    async def process(self, input_data: Any, **kwargs: Any) -> Any:
        if self._is_async:
            return await self._func(input_data, **kwargs)
        return self._func(input_data, **kwargs)

    def __repr__(self) -> str:
        return f"FunctionStep(name={self._step_name!r})"


class AgentStep(PipelineStep):
    """
    A pipeline step that runs an agent.

    Wraps an Agent instance and passes the input as the message.

    Usage:
        agent = Agent(name="assistant", model="gpt-4o")
        step = AgentStep(agent)
    """

    def __init__(self, agent: Any) -> None:
        self._agent = agent

    @property
    def name(self) -> str:
        return self._agent.name

    async def process(self, input_data: Any, **kwargs: Any) -> Any:
        if isinstance(input_data, str):
            message = input_data
        elif isinstance(input_data, dict):
            message = input_data.get("message", input_data.get("content", str(input_data)))
        else:
            message = str(input_data)

        response = await self._agent.run(message, **kwargs)

        if response.success:
            return response.content
        else:
            raise PipelineStop(
                message=f"Agent '{self._agent.name}' failed: {response.error}",
                modified_data=response.content,
            )

    def __repr__(self) -> str:
        return f"AgentStep(agent={self._agent.name!r})"


class GuardrailStep(PipelineStep):
    """
    A pipeline step that acts as a guardrail.

    Checks the input against a guardrail and either passes it through
    or stops the pipeline.

    Usage:
        guardrail = NoPIIGuardrail()
        step = GuardrailStep(guardrail)
    """

    def __init__(self, guardrail: Any) -> None:
        self._guardrail = guardrail

    @property
    def name(self) -> str:
        return f"Guardrail:{getattr(self._guardrail, '__class__', type(guardrail)).__name__}"

    async def process(self, input_data: Any, **kwargs: Any) -> Any:
        # Handle both sync and async guardrails
        if asyncio.iscoroutinefunction(self._guardrail.check):
            allowed, modified, reason = await self._guardrail.check(input_data)
        else:
            allowed, modified, reason = self._guardrail.check(input_data)

        if not allowed:
            raise PipelineStop(
                message=f"Guardrail blocked: {reason}",
                modified_data=modified,
            )

        return modified if modified is not None else input_data

    def __repr__(self) -> str:
        guardrail_name = getattr(
            self._guardrail, "__class__", type(self._guardrail)
        ).__name__
        return f"GuardrailStep(guardrail={guardrail_name!r})"


class ConditionalStep(PipelineStep):
    """
    A pipeline step that conditionally processes data.

    Only processes the input if the condition function returns True.

    Usage:
        step = ConditionalStep(
            condition=lambda x: len(x) > 10,
            inner_step=FunctionStep(my_func),
        )
    """

    def __init__(
        self,
        condition: Callable[[Any], bool],
        inner_step: PipelineStep,
        *,
        name: Optional[str] = None,
    ) -> None:
        self._condition = condition
        self._inner_step = inner_step
        self._step_name = name or f"Conditional:{inner_step.name}"

    @property
    def name(self) -> str:
        return self._step_name

    async def process(self, input_data: Any, **kwargs: Any) -> Any:
        if self._condition(input_data):
            return await self._inner_step.process(input_data, **kwargs)
        return input_data


class MapStep(PipelineStep):
    """
    A pipeline step that applies an inner step to each item in a list.

    Usage:
        step = MapStep(AgentStep(agent), name="batch_process")
    """

    def __init__(
        self,
        inner_step: PipelineStep,
        *,
        name: Optional[str] = None,
        parallel: bool = False,
        max_concurrency: int = 5,
    ) -> None:
        self._inner_step = inner_step
        self._step_name = name or f"Map:{inner_step.name}"
        self._parallel = parallel
        self._max_concurrency = max_concurrency

    @property
    def name(self) -> str:
        return self._step_name

    async def process(self, input_data: Any, **kwargs: Any) -> Any:
        if not isinstance(input_data, list):
            input_data = [input_data]

        if self._parallel:
            semaphore = asyncio.Semaphore(self._max_concurrency)

            async def _bounded_process(item: Any) -> Any:
                async with semaphore:
                    return await self._inner_step.process(item, **kwargs)

            return await asyncio.gather(
                *[_bounded_process(item) for item in input_data],
                return_exceptions=True,
            )
        else:
            results = []
            for item in input_data:
                result = await self._inner_step.process(item, **kwargs)
                results.append(result)
            return results


class AIPipeline:
    """
    Composable AI pipeline for chaining processing steps.

    Each step receives the output of the previous step. The pipeline
    handles errors, logging, and can be configured with a timeout.

    Usage:
        # Simple pipeline
        pipeline = AIPipeline(steps=[
            GuardrailStep(NoPIIGuardrail()),
            AgentStep(agent),
            FunctionStep(format_output, name="formatter"),
        ])
        result = await pipeline.run("Hello, world!")

        # With error handling
        result = await pipeline.run("Bad input")
        if not result.success:
            print(f"Pipeline failed: {result.error}")
    """

    def __init__(
        self,
        steps: Optional[List[PipelineStep]] = None,
        *,
        name: str = "pipeline",
        description: str = "",
        timeout: float = 300.0,
        stop_on_error: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._steps: List[PipelineStep] = steps or []
        self._name = name
        self._description = description
        self._timeout = timeout
        self._stop_on_error = stop_on_error
        self._metadata = metadata or {}
        self._hooks: Dict[str, List[Callable]] = {
            "before_step": [],
            "after_step": [],
            "on_error": [],
            "on_complete": [],
        }

    @property
    def name(self) -> str:
        """Get the pipeline name."""
        return self._name

    @property
    def steps(self) -> List[PipelineStep]:
        """Get the pipeline steps."""
        return list(self._steps)

    @property
    def step_count(self) -> int:
        """Get the number of steps."""
        return len(self._steps)

    # ---- Step Management ----

    def add_step(self, step: PipelineStep) -> AIPipeline:
        """
        Add a step to the end of the pipeline.

        Args:
            step: The PipelineStep to add.

        Returns:
            self for chaining.
        """
        self._steps.append(step)
        return self

    def insert_step(self, index: int, step: PipelineStep) -> AIPipeline:
        """
        Insert a step at a specific position.

        Args:
            index: The position to insert at.
            step: The PipelineStep to insert.

        Returns:
            self for chaining.
        """
        self._steps.insert(index, step)
        return self

    def remove_step(self, index: int) -> AIPipeline:
        """
        Remove a step at a specific position.

        Args:
            index: The position of the step to remove.

        Returns:
            self for chaining.
        """
        if 0 <= index < len(self._steps):
            self._steps.pop(index)
        return self

    def add_guardrail(self, guardrail: Any, *, position: int = 0) -> AIPipeline:
        """
        Add a guardrail step at a specific position.

        Args:
            guardrail: The guardrail instance.
            position: Where to insert (default: start of pipeline).

        Returns:
            self for chaining.
        """
        step = GuardrailStep(guardrail)
        self._steps.insert(position, step)
        return self

    # ---- Execution ----

    async def run(
        self,
        input_data: Any,
        **kwargs: Any,
    ) -> PipelineResult:
        """
        Run the pipeline with the given input.

        Executes each step sequentially, passing the output of one step
        to the next. If a step raises PipelineStop, the pipeline stops
        and returns the modified data.

        Args:
            input_data: The initial input to the pipeline.
            **kwargs: Additional context passed to all steps.

        Returns:
            A PipelineResult with the final output and metadata.
        """
        start_time = time.time()
        step_results: List[Dict[str, Any]] = []
        total_tokens = 0
        current_data = input_data

        try:
            for i, step in enumerate(self._steps):
                step_start = time.time()

                # Before-step hook
                await self._run_hooks("before_step", step=step, index=i, data=current_data)

                try:
                    # Execute step with timeout
                    result = await asyncio.wait_for(
                        step.process(current_data, **kwargs),
                        timeout=self._timeout,
                    )

                    step_duration = (time.time() - step_start) * 1000
                    step_results.append({
                        "step": step.name,
                        "index": i,
                        "success": True,
                        "duration_ms": step_duration,
                        "output_preview": str(result)[:200] if result else None,
                    })

                    current_data = result

                    # After-step hook
                    await self._run_hooks(
                        "after_step",
                        step=step,
                        index=i,
                        output=result,
                    )

                    # Track tokens from agent responses
                    if isinstance(result, dict) and "tokens_used" in result:
                        tokens = result["tokens_used"]
                        if isinstance(tokens, dict):
                            total_tokens += tokens.get("total", 0)
                        elif isinstance(tokens, int):
                            total_tokens += tokens

                except PipelineStop as stop:
                    step_duration = (time.time() - step_start) * 1000
                    step_results.append({
                        "step": step.name,
                        "index": i,
                        "success": False,
                        "duration_ms": step_duration,
                        "reason": stop.message,
                    })

                    # On-error hook
                    await self._run_hooks(
                        "on_error",
                        step=step,
                        index=i,
                        error=stop.message,
                    )

                    return PipelineResult(
                        output=stop.modified_data if stop.modified_data is not None else current_data,
                        step_results=step_results,
                        total_tokens=total_tokens,
                        duration_ms=(time.time() - start_time) * 1000,
                        success=False,
                        error=stop.message,
                        metadata=self._metadata,
                        stopped_at=i,
                    )

                except asyncio.TimeoutError:
                    step_duration = (time.time() - step_start) * 1000
                    step_results.append({
                        "step": step.name,
                        "index": i,
                        "success": False,
                        "duration_ms": step_duration,
                        "reason": "Timeout",
                    })

                    if self._stop_on_error:
                        return PipelineResult(
                            output=current_data,
                            step_results=step_results,
                            total_tokens=total_tokens,
                            duration_ms=(time.time() - start_time) * 1000,
                            success=False,
                            error=f"Step '{step.name}' timed out after {self._timeout}s",
                            metadata=self._metadata,
                            stopped_at=i,
                        )

                except Exception as e:
                    step_duration = (time.time() - step_start) * 1000
                    step_results.append({
                        "step": step.name,
                        "index": i,
                        "success": False,
                        "duration_ms": step_duration,
                        "reason": str(e),
                    })

                    await self._run_hooks(
                        "on_error",
                        step=step,
                        index=i,
                        error=e,
                    )

                    if self._stop_on_error:
                        return PipelineResult(
                            output=current_data,
                            step_results=step_results,
                            total_tokens=total_tokens,
                            duration_ms=(time.time() - start_time) * 1000,
                            success=False,
                            error=f"Step '{step.name}' error: {e}",
                            metadata=self._metadata,
                            stopped_at=i,
                        )

            # On-complete hook
            await self._run_hooks("on_complete", result=current_data)

            return PipelineResult(
                output=current_data,
                step_results=step_results,
                total_tokens=total_tokens,
                duration_ms=(time.time() - start_time) * 1000,
                success=True,
                metadata=self._metadata,
            )

        except Exception as e:
            return PipelineResult(
                output=current_data,
                step_results=step_results,
                total_tokens=total_tokens,
                duration_ms=(time.time() - start_time) * 1000,
                success=False,
                error=f"Pipeline error: {e}",
                metadata=self._metadata,
            )

    # ---- Hooks ----

    def on(self, event: str) -> Callable:
        """
        Register a pipeline lifecycle hook.

        Args:
            event: One of 'before_step', 'after_step', 'on_error', 'on_complete'.

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

    # ---- Composition ----

    def pipe(self, other: AIPipeline) -> AIPipeline:
        """
        Compose this pipeline with another, creating a new pipeline.

        The steps of the other pipeline are appended after this pipeline's steps.

        Args:
            other: Another AIPipeline to chain after this one.

        Returns:
            A new AIPipeline with combined steps.
        """
        return AIPipeline(
            steps=self._steps + other._steps,
            name=f"{self._name} -> {other._name}",
            metadata={**self._metadata, **other._metadata},
        )

    def __or__(self, other: AIPipeline) -> AIPipeline:
        """Support pipe operator: pipeline1 | pipeline2"""
        return self.pipe(other)

    def __repr__(self) -> str:
        step_names = [s.name for s in self._steps]
        return f"AIPipeline(name={self._name!r}, steps={step_names})"
