# GraphQL Module

GraphQL API with auto-schema generation and subscriptions.

## Setup

```python
from vorte import GraphQLModule

app.register(GraphQLModule())
```

## Configuration

```env
VORTE_GRAPHQL_ENABLED=true
VORTE_GRAPHQL_AUTO_SCHEMA=true
VORTE_GRAPHQL_PLAYGROUND=true
VORTE_GRAPHQL_SUBSCRIPTIONS=true
```

## Features

- **Auto-schema** -- Generate GraphQL schema from SQLAlchemy models
- **Playground** -- Interactive GraphQL Playground IDE
- **Subscriptions** -- Real-time data via WebSocket subscriptions
- **Query/Mutation Resolvers** -- Standard GraphQL resolver pattern
