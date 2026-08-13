"""Compatibility shim. Prefer ``doc_search.extract.word``."""

from .extract.word import WordExtractor, extract_word_text

__all__ = ['WordExtractor', 'extract_word_text']
