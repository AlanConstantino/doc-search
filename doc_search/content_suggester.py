"""Compatibility shim. Prefer ``doc_search.search.features.suggester``."""

from .search.features.suggester import ContentSuggester

__all__ = ['ContentSuggester']
