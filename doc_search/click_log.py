"""Compatibility shim. Prefer ``doc_search.search.features.clicks``."""

from .search.features.clicks import ClickLog

__all__ = ['ClickLog']
