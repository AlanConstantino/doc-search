"""Compatibility shim. Prefer ``doc_search.search.features.facets``."""

from .search.features.facets import FacetExtractor, FacetIndex

__all__ = ['FacetExtractor', 'FacetIndex']
