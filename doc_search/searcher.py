"""Compatibility shim. Prefer ``doc_search.search``."""

from .search.engine import (
    SearchEngine, EnhancedSearchEngine, SearchCache,
    parse_query, group_results_by_section, compute_index_fingerprint,
    document_has_phrases, find_phrase_positions,
)
from .search.snippets import (
    highlight_terms, find_best_snippet, check_phrase_match, normalize_document_text,
)
from .app.cli.formatters import format_results, highlight_terms_ansi

__all__ = [
    'SearchEngine', 'EnhancedSearchEngine', 'SearchCache',
    'parse_query', 'group_results_by_section', 'compute_index_fingerprint',
    'document_has_phrases', 'find_phrase_positions',
    'highlight_terms', 'highlight_terms_ansi', 'find_best_snippet',
    'check_phrase_match', 'normalize_document_text', 'format_results',
]
