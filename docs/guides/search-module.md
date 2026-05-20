# Search Module

Full-text search with MeiliSearch and pgvector support.

## Setup

```python
from vorte import SearchModule

app.register(SearchModule())
```

## Configuration

```env
VORTE_SEARCH_ENGINE=meilisearch
VORTE_SEARCH_MEILISEARCH_URL=http://localhost:7700
VORTE_SEARCH_MEILISEARCH_KEY=masterKey
```

## Features

- **MeiliSearch** -- Typo-tolerant full-text search
- **pgvector** -- Vector similarity search in PostgreSQL
- **Index Management** -- Create, list, delete indexes
- **Search API** -- Standard search interface

## CLI

```bash
vorte search:index list           # List indexes
vorte search:index create myindex # Create index
vorte search:index delete myindex # Delete index
```
