"""Compatibility shim. Prefer ``doc_search.extract.html``."""

from .extract.html import HTMLTextExtractor, extract_text, extract_links

__all__ = ['HTMLTextExtractor', 'extract_text', 'extract_links']
