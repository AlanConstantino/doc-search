"""Compatibility shim. Prefer ``doc_search.search.features.synonyms``."""

from .search.features.synonyms import (
    SynonymExpander, QueryExpander, load_synonyms_file, load_default_synonyms,
    DEFAULT_SYNONYM_GROUPS,
)

__all__ = [
    'SynonymExpander', 'QueryExpander', 'load_synonyms_file',
    'load_default_synonyms', 'DEFAULT_SYNONYM_GROUPS',
]
