"""Compatibility shim. Prefer ``doc_search.search.features.symspell``."""

from .search.features.symspell import SymSpell

__all__ = ['SymSpell']
