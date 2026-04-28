"""
Vorte Search Module — Search Engine & Backends
==============================================
Provides keyword, semantic, and hybrid search with pluggable backends
(Meilisearch, pgvector, database full-text).

Usage::

    engine = HybridSearchEngine(backend="meilisearch", meilisearch_url="http://localhost:7700")
    result = await engine.search("hello world", index="articles", filters={"status": "published"})
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, Sequence, TypeVar

logger = logging.getLogger("vorte.modules.search")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Result & filter types
# ---------------------------------------------------------------------------

@dataclass
class Highlight:
    """Highlighted snippet for a single field."""
    field: str
    value: str
    matched_tokens: List[str] = field(default_factory=list)


@dataclass
class SearchHit:
    """A single search result hit."""
    id: str
    score: float
    data: Dict[str, Any] = field(default_factory=dict)
    highlights: List[Highlight] = field(default_factory=list)


@dataclass
class FacetResult:
    """Faceted-count result for a single attribute."""
    field: str
    counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class SearchFilters:
    """Structured filter descriptor for a search query."""
    eq: Dict[str, Any] = field(default_factory=dict)
    neq: Dict[str, Any] = field(default_factory=dict)
    in_: Dict[str, List[Any]] = field(default_factory=dict)
    gt: Dict[str, Any] = field(default_factory=dict)
    gte: Dict[str, Any] = field(default_factory=dict)
    lt: Dict[str, Any] = field(default_factory=dict)
    lte: Dict[str, Any] = field(default_factory=dict)
    range: Dict[str, tuple] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"eq": self.eq, "neq": self.neq, "in": self.in_,
                             "gt": self.gt, "gte": self.gte, "lt": self.lt, "lte": self.lte}
        return d


@dataclass
class SearchResult:
    """Aggregated result returned by the search engine."""
    query: str
    hits: List[SearchHit] = field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0
    facets: List[FacetResult] = field(default_factory=list)
    processing_time_ms: int = 0

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.limit) if self.limit else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "total_pages": self.total_pages,
            "processing_time_ms": self.processing_time_ms,
            "hits": [
                {
                    "id": h.id,
                    "score": h.score,
                    "data": h.data,
                    "highlights": [
                        {"field": hl.field, "value": hl.value, "matched_tokens": hl.matched_tokens}
                        for hl in h.highlights
                    ],
                }
                for h in self.hits
            ],
            "facets": {f.field: f.counts for f in self.facets},
        }


# ---------------------------------------------------------------------------
# Abstract backend
# ---------------------------------------------------------------------------

class SearchBackend(abc.ABC):
    """Interface that every search backend must implement."""

    @abc.abstractmethod
    async def ping(self) -> bool:
        """Check if the backend is reachable."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Close any open connections."""

    @abc.abstractmethod
    async def search(
        self,
        query: str,
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        facet_fields: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
        highlight: bool = True,
        highlight_pre_tag: str = "<mark>",
        highlight_post_tag: str = "</mark>",
    ) -> SearchResult:
        """Execute a keyword search query."""

    @abc.abstractmethod
    async def vector_search(
        self,
        embedding: List[float],
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> SearchResult:
        """Execute a semantic / vector proximity search."""

    @abc.abstractmethod
    async def index_document(self, index: str, doc_id: str, document: Dict[str, Any],
                             embedding: Optional[List[float]] = None) -> None:
        """Index (or re-index) a single document."""

    @abc.abstractmethod
    async def delete_document(self, index: str, doc_id: str) -> None:
        """Remove a document from the index."""

    @abc.abstractmethod
    async def create_index(self, index: str, **kwargs: Any) -> Dict[str, Any]:
        """Create a search index."""

    @abc.abstractmethod
    async def list_indexes(self) -> List[str]:
        """List all indexes."""


# ---------------------------------------------------------------------------
# Meilisearch backend
# ---------------------------------------------------------------------------

class MeilisearchBackend(SearchBackend):
    """
    Meilisearch search backend.

    Requires ``meilisearch`` pip package.  Falls back gracefully when the
    package is not installed.
    """

    def __init__(
        self,
        url: str = "http://localhost:7700",
        api_key: str = "",
        default_limit: int = 20,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._default_limit = default_limit
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import meilisearch
            self._client = meilisearch.Client(self._url, self._api_key)
        except ImportError:
            raise RuntimeError("meilisearch package is required.  pip install meilisearch")
        return self._client

    async def ping(self) -> bool:
        try:
            client = self._get_client()
            return bool(client.is_healthy())
        except Exception:
            return False

    async def close(self) -> None:
        self._client = None

    async def search(
        self,
        query: str,
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        facet_fields: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
        highlight: bool = True,
        highlight_pre_tag: str = "<mark>",
        highlight_post_tag: str = "</mark>",
    ) -> SearchResult:
        client = self._get_client()
        if not index:
            raise ValueError("Meilisearch requires an index name")

        idx = client.get_index(index)
        search_params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if filters:
            search_params["filter"] = self._build_filter_string(filters)
        if facet_fields:
            search_params["facets"] = facet_fields
        if highlight:
            search_params["attributesToHighlight"] = ["*"]
            search_params["highlightPreTag"] = highlight_pre_tag
            search_params["highlightPostTag"] = highlight_post_tag

        resp = await asyncio.to_thread(idx.search, query, search_params)

        hits: List[SearchHit] = []
        for h in resp.get("hits", []):
            hl = []
            formatted = h.pop("_formatted", None) or {}
            if formatted:
                for fk, fv in formatted.items():
                    if isinstance(fv, str) and highlight_pre_tag in fv:
                        hl.append(Highlight(field=fk, value=fv))
            hits.append(SearchHit(id=str(h.get("id", "")), score=h.get("_rankingScore", 0.0), data=h, highlights=hl))

        facets = []
        if facet_fields and "facetalDistribution" in resp:
            for ff, counts in resp["facetalDistribution"].items():
                facets.append(FacetResult(field=ff, counts={str(k): v for k, v in counts.items()}))

        return SearchResult(
            query=query,
            hits=hits,
            total=resp.get("estimatedTotalHits", 0),
            limit=limit,
            offset=offset,
            facets=facets,
            processing_time_ms=resp.get("processingTimeMs", 0),
        )

    async def vector_search(
        self,
        embedding: List[float],
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> SearchResult:
        # Meilisearch supports vector search via the hybrid endpoint (v1.3+)
        client = self._get_client()
        if not index:
            raise ValueError("Index required")
        idx = client.get_index(index)
        params: Dict[str, Any] = {"vector": embedding, "limit": limit}
        if filters:
            params["filter"] = self._build_filter_string(filters)
        try:
            resp = await asyncio.to_thread(idx.search, "", params)
            hits = [
                SearchHit(id=str(h.get("id", "")), score=h.get("_rankingScore", 0.0), data=h)
                for h in resp.get("hits", [])
            ]
            return SearchResult(query="", hits=hits, total=resp.get("estimatedTotalHits", 0), limit=limit)
        except Exception as exc:
            logger.warning("Meilisearch vector search failed: %s", exc)
            return SearchResult(query="", hits=[], total=0, limit=limit)

    async def index_document(self, index: str, doc_id: str, document: Dict[str, Any],
                             embedding: Optional[List[float]] = None) -> None:
        client = self._get_client()
        document["id"] = doc_id
        if embedding:
            document["_vectors"] = {"embedding": embedding}
        await asyncio.to_thread(client.index(index).add_documents, [document])

    async def delete_document(self, index: str, doc_id: str) -> None:
        client = self._get_client()
        await asyncio.to_thread(client.index(index).delete_document, doc_id)

    async def create_index(self, index: str, **kwargs: Any) -> Dict[str, Any]:
        client = self._get_client()
        task = await asyncio.to_thread(client.create_index, index, {"primaryKey": kwargs.get("primary_key", "id")})
        return {"task_uid": task.task_uid}

    async def list_indexes(self) -> List[str]:
        client = self._get_client()
        indexes = await asyncio.to_thread(client.get_indexes)
        return [idx.uid for idx in indexes]

    # -- helpers --

    @staticmethod
    def _build_filter_string(filters: Dict[str, Any]) -> str:
        """Build a Meilisearch filter expression from a dict."""
        parts: List[str] = []
        for key, val in filters.items():
            if isinstance(val, list):
                parts.append(f"{key} IN {json.dumps(val)}")
            elif isinstance(val, dict):
                for op, v in val.items():
                    parts.append(f"{key} {op} {json.dumps(v)}")
            else:
                parts.append(f"{key} = {json.dumps(val)}")
        return " AND ".join(parts)


# ---------------------------------------------------------------------------
# pgvector backend
# ---------------------------------------------------------------------------

class PgVectorBackend(SearchBackend):
    """
    PostgreSQL + pgvector search backend.

    Provides full-text search via ``tsvector`` and semantic search via
    the ``vector`` extension (pgvector).  Falls back when ``asyncpg`` or
    ``pgvector`` is not available.
    """

    def __init__(
        self,
        connection_string: str = "",
        default_limit: int = 20,
        embedding_dim: int = 1536,
    ) -> None:
        self._connection_string = connection_string
        self._default_limit = default_limit
        self._embedding_dim = embedding_dim
        self._pool: Optional[Any] = None

    async def _get_pool(self) -> Any:
        if self._pool is not None:
            return self._pool
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(self._connection_string, min_size=2, max_size=10)
        except ImportError:
            raise RuntimeError("asyncpg package is required.  pip install asyncpg")
        return self._pool

    async def ping(self) -> bool:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def search(
        self,
        query: str,
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        facet_fields: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
        highlight: bool = True,
        highlight_pre_tag: str = "<mark>",
        highlight_post_tag: str = "</mark>",
    ) -> SearchResult:
        pool = await self._get_pool()
        table = index or "search_documents"

        where_clauses = ["to_tsvector('english', content) @@ plainto_tsquery('english', $1)"]
        params: List[Any] = [query]
        idx = 2

        if filters:
            for k, v in filters.items():
                where_clauses.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1

        where = " AND ".join(where_clauses)
        count_sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
        data_sql = (
            f"SELECT id, content, data, ts_rank(to_tsvector('english', content), plainto_tsquery('english', $1)) AS rank "
            f"FROM {table} WHERE {where} ORDER BY rank DESC LIMIT ${idx} OFFSET ${idx + 1}"
        )
        params += [limit, offset]

        async with pool.acquire() as conn:
            total = await conn.fetchval(count_sql, *params[:idx - 2])
            rows = await conn.fetch(data_sql, *params)

        hits = []
        for row in rows:
            data = dict(row.get("data") or {})
            hits.append(SearchHit(id=str(row["id"]), score=float(row["rank"] or 0), data=data))

        return SearchResult(query=query, hits=hits, total=total or 0, limit=limit, offset=offset)

    async def vector_search(
        self,
        embedding: List[float],
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> SearchResult:
        pool = await self._get_pool()
        table = index or "search_documents"

        where = ""
        params: List[Any] = []
        idx = 1
        if filters:
            parts = []
            for k, v in filters.items():
                parts.append(f"{k} = ${idx}")
                params.append(v)
                idx += 1
            where = "WHERE " + " AND ".join(parts)

        sql = (
            f"SELECT id, data, 1 - (embedding <=> $1::vector) AS similarity "
            f"FROM {table} {where} ORDER BY embedding <=> $1::vector LIMIT ${idx}"
        )
        params = [embedding] + params + [limit]

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        hits = [SearchHit(id=str(r["id"]), score=float(r["similarity"]), data=dict(r["data"] or {})) for r in rows]
        return SearchResult(query="", hits=hits, total=len(hits), limit=limit)

    async def index_document(self, index: str, doc_id: str, document: Dict[str, Any],
                             embedding: Optional[List[float]] = None) -> None:
        pool = await self._get_pool()
        table = index
        content = document.pop("content", "")
        data = json.dumps(document)
        emb_str = f"'[{','.join(str(x) for x in embedding)}]'" if embedding else "NULL"
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {table} (id, content, data, embedding)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (id) DO UPDATE SET content=$2, data=$3, embedding=$4
                """,
                doc_id, content, data, embedding,
            )

    async def delete_document(self, index: str, doc_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {index} WHERE id = $1", doc_id)

    async def create_index(self, index: str, **kwargs: Any) -> Dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {index} (
                    id TEXT PRIMARY KEY,
                    content TEXT,
                    data JSONB,
                    embedding vector({kwargs.get('embedding_dim', self._embedding_dim)})
                )
                """
            )
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{index}_fts ON {index} USING GIN(to_tsvector('english', content))")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{index}_vec ON {index} USING ivfflat (embedding vector_cosine_ops)")
        return {"index": index, "status": "created"}

    async def list_indexes(self) -> List[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'search_%'"
            )
        return [r["tablename"] for r in rows]


# ---------------------------------------------------------------------------
# Hybrid search engine
# ---------------------------------------------------------------------------

class HybridSearchEngine:
    """
    Unified search engine that combines keyword and vector search.

    Usage::

        engine = HybridSearchEngine(backend="meilisearch", meilisearch_url="http://...")
        result = await engine.search("hello", index="posts")
    """

    BACKEND_MAP = {
        "meilisearch": MeilisearchBackend,
        "pgvector": PgVectorBackend,
    }

    def __init__(
        self,
        backend: str = "database",
        meilisearch_url: str = "",
        meilisearch_key: str = "",
        pgvector_connection: str = "",
        **kwargs: Any,
    ) -> None:
        backend_cls = self.BACKEND_MAP.get(backend)
        if backend_cls:
            if backend == "meilisearch":
                self.backend: Optional[SearchBackend] = MeilisearchBackend(url=meilisearch_url, api_key=meilisearch_key)
            elif backend == "pgvector":
                self.backend = PgVectorBackend(connection_string=pgvector_connection)
            else:
                self.backend = backend_cls(**kwargs)
        else:
            self.backend = None

    async def search(
        self,
        query: str,
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        facet_fields: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
        highlight: bool = True,
        highlight_pre_tag: str = "<mark>",
        highlight_post_tag: str = "</mark>",
    ) -> SearchResult:
        """Execute a keyword search against the configured backend."""
        if self.backend:
            return await self.backend.search(
                query=query,
                index=index,
                filters=filters,
                facet_fields=facet_fields,
                limit=limit,
                offset=offset,
                highlight=highlight,
                highlight_pre_tag=highlight_pre_tag,
                highlight_post_tag=highlight_post_tag,
            )
        return SearchResult(query=query, hits=[], total=0, limit=limit, offset=offset)

    async def vector_search(
        self,
        embedding: List[float],
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> SearchResult:
        """Execute a vector / semantic search."""
        if self.backend:
            return await self.backend.vector_search(embedding=embedding, index=index, filters=filters, limit=limit)
        return SearchResult(query="", hits=[], total=0, limit=limit)

    async def hybrid_search(
        self,
        query: str,
        embedding: List[float],
        index: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        alpha: float = 0.5,
    ) -> SearchResult:
        """
        Combine keyword and vector results using reciprocal rank fusion.

        Args:
            query: text query for keyword search
            embedding: vector embedding for semantic search
            index: search index
            filters: optional filters
            limit: number of results
            alpha: weight for keyword results (0-1). 1.0 = keyword only, 0.0 = vector only.
        """
        keyword_result = await self.search(query=query, index=index, filters=filters, limit=limit * 2)
        vector_result = await self.vector_search(embedding=embedding, index=index, filters=filters, limit=limit * 2)

        # Reciprocal Rank Fusion
        scores: Dict[str, float] = {}
        hit_data: Dict[str, SearchHit] = {}

        for rank, hit in enumerate(keyword_result.hits):
            doc_id = hit.id
            scores[doc_id] = scores.get(doc_id, 0) + alpha / (60 + rank + 1)
            hit_data[doc_id] = hit

        for rank, hit in enumerate(vector_result.hits):
            doc_id = hit.id
            scores[doc_id] = scores.get(doc_id, 0) + (1 - alpha) / (60 + rank + 1)
            if doc_id not in hit_data:
                hit_data[doc_id] = hit

        sorted_ids = sorted(scores, key=scores.get, reverse=True)[:limit]
        hits = [SearchHit(id=doc_id, score=scores[doc_id], data=hit_data[doc_id].data) for doc_id in sorted_ids]

        return SearchResult(
            query=query,
            hits=hits,
            total=len(hits),
            limit=limit,
        )

    async def index_document(self, index: str, doc_id: str, document: Dict[str, Any],
                             embedding: Optional[List[float]] = None) -> None:
        if self.backend:
            await self.backend.index_document(index, doc_id, document, embedding)

    async def delete_document(self, index: str, doc_id: str) -> None:
        if self.backend:
            await self.backend.delete_document(index, doc_id)


# ---------------------------------------------------------------------------
# SearchableMixin
# ---------------------------------------------------------------------------

class SearchableMixin:
    """
    Mixin for SQLAlchemy / Tortoise ORM models to make them searchable.

    Usage::

        class Article(SearchableMixin, Base):
            __search_index__ = "articles"
            __search_fields__ = ["title", "body"]

            id = Column(Integer, primary_key=True)
            title = Column(String)
            body = Column(Text)

        # Index an instance
        await article.search_index(engine)

        # Search
        results = await Article.search(engine, "hello world")
    """

    __search_index__: str = ""
    __search_fields__: List[str] = []

    @classmethod
    def _search_payload(cls) -> Dict[str, Any]:
        """Build the document payload to be sent to the search engine."""
        payload: Dict[str, Any] = {}
        for f in cls.__search_fields__:
            if hasattr(cls, f):
                payload[f] = getattr(cls, f)
        return payload

    async def search_index(self, engine: HybridSearchEngine, embedding: Optional[List[float]] = None) -> None:
        """Index this model instance."""
        doc = self._search_payload()
        doc_id = str(getattr(self, "id", ""))
        await engine.index_document(self.__search_index__, doc_id, doc, embedding)

    async def search_remove(self, engine: HybridSearchEngine) -> None:
        """Remove this model instance from the index."""
        doc_id = str(getattr(self, "id", ""))
        await engine.delete_document(self.__search_index__, doc_id)

    @classmethod
    async def search(
        cls,
        engine: HybridSearchEngine,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResult:
        """Search for model instances."""
        return await engine.search(query=query, index=cls.__search_index__, filters=filters, limit=limit, offset=offset)
