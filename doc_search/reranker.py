"""Compatibility shim. Prefer ``doc_search.search.features.reranker``."""

from .search.features.reranker import (
    Reranker, RerankConfig, RerankMetrics, check_phrase_proximity,
)

__all__ = ['Reranker', 'RerankConfig', 'RerankMetrics', 'check_phrase_proximity']
