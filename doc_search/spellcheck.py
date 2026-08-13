"""Compatibility shim. Prefer ``doc_search.search.features.spellcheck``."""

from .search.features.spellcheck import SpellChecker, damerau_levenshtein_distance

__all__ = ['SpellChecker', 'damerau_levenshtein_distance']
