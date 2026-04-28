"""
Tool System for Agents
======================
Function calling / tool use system for agents. Supports defining tools as
Python functions with type hints, auto-generates JSON schemas from function
signatures, and handles both sync and async tool execution.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints

# Mapping from Python types to JSON Schema types
_TYPE_MAP: Dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

# Additional mapping for complex types from typing module
_TYPING_MAP: Dict[str, str] = {
    "List": "array",
    "Dict": "object",
    "Optional": "string",
    "Union": "string",
}


@dataclass
class ToolParameter:
    """Describes a single parameter of a tool."""
    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None

    def to_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema property dict."""
        schema: Dict[str, Any] = {"type": self.type}

        if self.description:
            schema["description"] = self.description

        if self.enum:
            schema["enum"] = self.enum

        if not self.required and self.default is not None:
            schema["default"] = self.default

        return schema


@dataclass
class ToolSchema:
    """JSON Schema representation of a tool for LLM function calling."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_openai(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    """Result of executing a tool."""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    duration_ms: float = 0.0


class Tool:
    """
    Represents a callable tool that an agent can use.

    Wraps a Python function with metadata for schema generation and
    supports both sync and async execution.

    Usage:
        # Using the decorator
        @tool(name="calculate", description="Perform a calculation")
        def calculate(expression: str) -> float:
            return eval(expression)

        # Or creating directly
        tool = Tool(
            name="search",
            description="Search for information",
            func=search_function,
            parameters=[...],
        )
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[List[ToolParameter]] = None,
        auto_schema: bool = True,
    ) -> None:
        self._name = name
        self._description = description
        self._func = func
        self._is_async = asyncio.iscoroutinefunction(func)
        self._parameters: List[ToolParameter] = parameters or []

        if auto_schema and not parameters:
            self._parameters = self._generate_parameters()

        self._schema = self._build_schema()

    @property
    def name(self) -> str:
        """Tool name."""
        return self._name

    @property
    def description(self) -> str:
        """Tool description."""
        return self._description

    @property
    def func(self) -> Callable:
        """Underlying function."""
        return self._func

    @property
    def is_async(self) -> bool:
        """Whether the tool function is async."""
        return self._is_async

    @property
    def parameters(self) -> List[ToolParameter]:
        """Tool parameter definitions."""
        return list(self._parameters)

    @property
    def schema(self) -> ToolSchema:
        """Tool JSON schema."""
        return self._schema

    def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool synchronously.

        Args:
            **kwargs: Arguments matching the tool's parameters.

        Returns:
            A ToolResult with the execution outcome.
        """
        import time
        start = time.time()
        try:
            result = self._func(**kwargs)
            duration_ms = (time.time() - start) * 1000
            return ToolResult(
                tool_name=self._name,
                success=True,
                result=result,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return ToolResult(
                tool_name=self._name,
                success=False,
                result=None,
                error=str(e),
                duration_ms=duration_ms,
            )

    async def aexecute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool asynchronously.

        Args:
            **kwargs: Arguments matching the tool's parameters.

        Returns:
            A ToolResult with the execution outcome.
        """
        import time
        start = time.time()
        try:
            if self._is_async:
                result = await self._func(**kwargs)
            else:
                result = self._func(**kwargs)
            duration_ms = (time.time() - start) * 1000
            return ToolResult(
                tool_name=self._name,
                success=True,
                result=result,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return ToolResult(
                tool_name=self._name,
                success=False,
                result=None,
                error=str(e),
                duration_ms=duration_ms,
            )

    def _generate_parameters(self) -> List[ToolParameter]:
        """Auto-generate ToolParameter list from function signature."""
        params: List[ToolParameter] = []
        sig = inspect.signature(self._func)

        try:
            hints = get_type_hints(self._func)
        except Exception:
            hints = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # Determine type
            raw_type = hints.get(param_name, str)
            json_type = _TYPE_MAP.get(raw_type, "string")

            # Check for Optional (has default or is annotated with Optional)
            has_default = param.default is not inspect.Parameter.empty
            required = not has_default

            # Extract default value
            default = None
            if has_default:
                default = param.default

            # Build description from docstring or parameter name
            description = self._extract_param_description(param_name)

            params.append(
                ToolParameter(
                    name=param_name,
                    type=json_type,
                    description=description,
                    required=required,
                    default=default,
                )
            )

        return params

    def _extract_param_description(self, param_name: str) -> str:
        """Try to extract parameter description from the function docstring."""
        if not self._func.__doc__:
            return ""

        doc = self._func.__doc__.strip()
        lines = doc.split("\n")

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(param_name):
                # Try pattern: "param_name: description"
                if ":" in stripped:
                    return stripped.split(":", 1)[1].strip()
                # Try pattern: "param_name - description"
                if " - " in stripped:
                    return stripped.split(" - ", 1)[1].strip()

        return ""

    def _build_schema(self) -> ToolSchema:
        """Build the ToolSchema from parameters."""
        properties = OrderedDict()
        required_params: List[str] = []

        for param in self._parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required_params.append(param.name)

        parameters: Dict[str, Any] = {
            "type": "object",
            "properties": dict(properties),
        }

        if required_params:
            parameters["required"] = required_params

        return ToolSchema(
            name=self._name,
            description=self._description,
            parameters=parameters,
        )

    def __repr__(self) -> str:
        return f"Tool(name={self._name!r}, params={len(self._parameters)})"


class ToolRegistry:
    """
    Registry for managing tools available to agents.

    Usage:
        registry = ToolRegistry()
        registry.register(my_tool)
        registry.register_from_callable(search_fn)

        schema = registry.get_openai_schemas()
        result = await registry.execute("calculate", expression="2+2")
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """
        Register a Tool instance.

        Args:
            tool: The Tool to register.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered. "
                f"Use replace() to overwrite."
            )
        self._tools[tool.name] = tool

    def replace(self, tool: Tool) -> None:
        """
        Replace an existing tool registration.

        Args:
            tool: The Tool to register (overwrites existing).
        """
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """
        Unregister a tool by name.

        Args:
            name: The tool name to remove.
        """
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        """
        Get a tool by name.

        Args:
            name: The tool name.

        Returns:
            The Tool instance or None.
        """
        return self._tools.get(name)

    def has_tools(self) -> bool:
        """Check if any tools are registered."""
        return len(self._tools) > 0

    def list_tools(self) -> List[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_tool_names(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_schemas(self) -> List[ToolSchema]:
        """Get schemas for all registered tools."""
        return [tool.schema for tool in self._tools.values()]

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        """Get all tool schemas in OpenAI function calling format."""
        return [tool.schema.to_openai() for tool in self._tools.values()]

    def register_from_callable(
        self,
        func: Callable,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Tool:
        """
        Register a tool from a plain Python function.

        Auto-generates the tool schema from the function's type hints and
        docstring.

        Args:
            func: The Python function to wrap as a tool.
            name: Override tool name (defaults to function name).
            description: Override description (defaults to function docstring).

        Returns:
            The created Tool instance.
        """
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip().split("\n")[0]

        tool = Tool(
            name=tool_name,
            description=tool_desc,
            func=func,
        )
        self.register(tool)
        return tool

    async def execute(self, name: str, **kwargs: Any) -> Any:
        """
        Execute a registered tool by name.

        Args:
            name: The tool name.
            **kwargs: Arguments to pass to the tool.

        Returns:
            The tool execution result.

        Raises:
            KeyError: If the tool is not found.
            RuntimeError: If tool execution fails.
        """
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Tool '{name}' is not registered.")

        result = await tool.aexecute(**kwargs)

        if not result.success:
            raise RuntimeError(
                f"Tool '{name}' execution failed: {result.error}"
            )

        return result.result

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={list(self._tools.keys())})"


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable:
    """
    Decorator to convert a function into a Tool.

    Usage:
        @tool(name="search", description="Search the web")
        async def search_web(query: str, num_results: int = 5) -> list:
            ...

    Args:
        name: Tool name (defaults to function name).
        description: Tool description (defaults to first line of docstring).

    Returns:
        Decorated function that is also a Tool instance.
    """
    def decorator(func: Callable) -> Tool:
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip().split("\n")[0]
        return Tool(
            name=tool_name,
            description=tool_desc,
            func=func,
        )
    return decorator
