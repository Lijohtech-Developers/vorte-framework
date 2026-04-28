"""
Vorte Search Module
====================
Full-text search with keyword, semantic (vector), and hybrid modes.
Supports Meilisearch and pgvector backends with filters, facets, and highlighting.
"""

from vorte.modules.search.module import SearchModule
from vorte.modules.search.search import (
    SearchBackend,
    MeilisearchBackend,
    PgVectorBackend,
    HybridSearchEngine,
    SearchableMixin,
    SearchResult,
    SearchFilters,
    FacetResult,
)

__all__ = [
    "SearchModule",
    "SearchBackend",
    "MeilisearchBackend",
    "PgVectorBackend",
    "HybridSearchEngine",
    "SearchableMixin",
    "SearchResult",
    "SearchFilters",
    "FacetResult",
]
