"""
Vorte GraphQL Module
====================
Native GraphQL support with auto-schema generation, playground, and subscriptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from vorte.core.module import Module, ModuleMeta, ModulePriority


@dataclass
class GraphQLField:
    name: str
    resolver: Callable
    return_type: Optional[Type] = None
    args: Dict[str, Type] = field(default_factory=dict)
    description: str = ""


@dataclass
class GraphQLSchema:
    query_fields: Dict[str, GraphQLField] = field(default_factory=dict)
    mutation_fields: Dict[str, GraphQLField] = field(default_factory=dict)
    subscription_fields: Dict[str, GraphQLField] = field(default_factory=dict)


class GraphQLBuilder:
    """Builds a GraphQL schema from registered queries, mutations, and subscriptions."""

    def __init__(self):
        self._queries: Dict[str, GraphQLField] = {}
        self._mutations: Dict[str, GraphQLField] = {}
        self._subscriptions: Dict[str, GraphQLField] = {}
        self._types: Dict[str, Dict[str, Any]] = {}

    def query(self, name: str, description: str = ""):
        """Decorator to register a GraphQL query."""
        def decorator(func: Callable) -> Callable:
            import inspect
            sig = inspect.signature(func)
            args = {}
            for pname, param in sig.parameters.items():
                if pname != 'self':
                    args[pname] = param.annotation if param.annotation != inspect.Parameter.empty else str
            self._queries[name] = GraphQLField(name=name, resolver=func, args=args, description=description)
            return func
        return decorator

    def mutation(self, name: str, description: str = ""):
        """Decorator to register a GraphQL mutation."""
        def decorator(func: Callable) -> Callable:
            import inspect
            sig = inspect.signature(func)
            args = {}
            for pname, param in sig.parameters.items():
                if pname != 'self':
                    args[pname] = param.annotation if param.annotation != inspect.Parameter.empty else str
            self._mutations[name] = GraphQLField(name=name, resolver=func, args=args, description=description)
            return func
        return decorator

    def subscription(self, name: str, description: str = ""):
        """Decorator to register a GraphQL subscription."""
        def decorator(func: Callable) -> Callable:
            self._subscriptions[name] = GraphQLField(name=name, resolver=func, description=description)
            return func
        return decorator

    def build_schema_string(self) -> str:
        """Build a GraphQL SDL schema string."""
        lines = ["type Query {"]
        for name, q in self._queries.items():
            args_str = ", ".join(f"{aname}: {atype.__name__ if hasattr(atype, '__name__') else atype}" for aname, atype in q.args.items())
            if args_str:
                lines.append(f"  {name}({args_str}): JSON")
            else:
                lines.append(f"  {name}: JSON")
        lines.append("}")
        lines.append("")
        if self._mutations:
            lines.append("type Mutation {")
            for name, m in self._mutations.items():
                lines.append(f"  {name}(input: JSON!): JSON")
            lines.append("}")
            lines.append("")
        if self._subscriptions:
            lines.append("type Subscription {")
            for name, s in self._subscriptions.items():
                lines.append(f"  {name}: JSON")
            lines.append("}")
        return "\n".join(lines)

    def get_schema(self) -> GraphQLSchema:
        return GraphQLSchema(
            query_fields=self._queries,
            mutation_fields=self._mutations,
            subscription_fields=self._subscriptions,
        )

    def list_operations(self) -> Dict[str, List[str]]:
        return {
            "queries": list(self._queries.keys()),
            "mutations": list(self._mutations.keys()),
            "subscriptions": list(self._subscriptions.keys()),
        }


GRAPHQL_PLAYGROUND_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Vorte GraphQL Playground</title>
    <style>
        body { margin: 0; font-family: -apple-system, sans-serif; background: #f5f5f5; }
        .container { max-width: 900px; margin: 40px auto; padding: 20px; }
        h1 { color: #333; margin-bottom: 20px; }
        .schema { background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        pre { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 6px; overflow-x: auto; font-size: 14px; }
        .operations { margin-top: 20px; }
        .op { display: inline-block; background: #e3f2fd; padding: 4px 12px; border-radius: 4px; margin: 4px; font-size: 13px; color: #1565c0; }
    </style>
</head>
<body>
<div class="container">
    <h1>Vorte GraphQL</h1>
    <div class="schema"><pre id="schema"></pre></div>
    <div class="operations" id="ops"></div>
</div>
<script>
fetch('/graphql/schema').then(r=>r.json()).then(d=>{
    document.getElementById('schema').textContent = d.data.schema;
    const ops = d.data.operations;
    let html = '';
    if (ops.queries.length) html += '<h3>Queries</h3>' + ops.queries.map(o=>`<span class="op">${o}</span>`).join('');
    if (ops.mutations.length) html += '<h3>Mutations</h3>' + ops.mutations.map(o=>`<span class="op">${o}</span>`).join('');
    if (ops.subscriptions.length) html += '<h3>Subscriptions</h3>' + ops.subscriptions.map(o=>`<span class="op">${o}</span>`).join('');
    document.getElementById('ops').innerHTML = html;
});
</script>
</body>
</html>
"""


class GraphQLModule(Module):
    """
    GraphQL module with auto-schema, playground, and subscriptions.
    
    Usage:
        app.register(GraphQLModule(auto_schema=True, playground=True))
        
        @graphql.query async def user(id: str): ...
        @graphql.mutation async def create_user(input: dict): ...
        @graphql.subscription async def user_created(): ...
    """

    meta = ModuleMeta(
        name="graphql",
        version="1.0.0",
        description="GraphQL support with auto-schema, playground, and subscriptions",
        priority=ModulePriority.ROUTES,
    )

    def __init__(self, *, auto_schema: bool = True, playground: bool = True, subscriptions: bool = True):
        super().__init__(auto_schema=auto_schema, playground=playground, subscriptions=subscriptions)
        self._auto_schema = auto_schema
        self._playground = playground
        self._subscriptions = subscriptions
        self._builder: Optional[GraphQLBuilder] = None

    def register(self, app) -> None:
        self._builder = GraphQLBuilder()
        if hasattr(app, 'container'):
            app.container.register_instance(GraphQLBuilder, self._builder)
        app.graphql = self._builder

        @app.post("/graphql")
        async def graphql_endpoint(request: Request):
            import json
            body = await request.json()
            query = body.get("query", "")
            operation_name = body.get("operationName")
            variables = body.get("variables", {})

            # Simple execution
            result = await self._execute(query, variables)
            return JSONResponse(content=result)

        @app.get("/graphql/schema")
        async def graphql_schema():
            schema = self._builder.build_schema_string()
            ops = self._builder.list_operations()
            return JSONResponse(content={"data": {"schema": schema, "operations": ops}})

        if self._playground:
            @app.get("/graphql/playground")
            async def graphql_playground():
                return HTMLResponse(content=GRAPHQL_PLAYGROUND_HTML)

    async def _execute(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a GraphQL query (simplified implementation)."""
        # Simple parser: detect operation type and field name
        query_type = "query"
        field_name = ""
        if "mutation" in query:
            query_type = "mutation"
        elif "subscription" in query:
            query_type = "subscription"
        
        # Extract field name (very simplified)
        parts = query.split("{")
        if len(parts) > 1:
            inner = parts[-1].strip().rstrip("}")
            field_name = inner.split("(")[0].split("{")[0].strip()
        
        # Find and execute resolver
        fields_map = {
            "query": self._builder._queries,
            "mutation": self._builder._mutations,
            "subscription": self._builder._subscriptions,
        }
        field = fields_map.get(query_type, {}).get(field_name)
        if field:
            try:
                result = field.resolver(**variables)
                if hasattr(result, '__await__'):
                    result = await result
                return {"data": {field_name: result}}
            except Exception as e:
                return {"errors": [{"message": str(e)}]}
        
        return {"errors": [{"message": f"Field '{field_name}' not found"}]}
