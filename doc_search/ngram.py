"""Compatibility shim. Prefer ``doc_search.search.features.ngram``."""

from .search.features.ngram import NGramIndex

__all__ = ['NGramIndex']
