"""Compatibility shim. Prefer ``doc_search.index``."""

from .index.store import (
    BM25Index, find_index_path, is_suggestion_worthy, filter_suggestion_terms,
    INDEX_FORMAT_VERSION,
)

__all__ = [
    'BM25Index', 'find_index_path', 'is_suggestion_worthy',
    'filter_suggestion_terms', 'INDEX_FORMAT_VERSION',
]
