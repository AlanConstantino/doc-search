"""Search layer: engines, snippets, optional features.

Depends on ``core`` and ``index``. Does not import ``app``.
"""

from .engine import (
    SearchEngine,
    EnhancedSearchEngine,
    SearchCache,
    parse_query,
    group_results_by_section,
    compute_index_fingerprint,
    document_has_phrases,
    find_phrase_positions,
)
from .snippets import (
    highlight_terms,
    find_best_snippet,
    check_phrase_match,
    normalize_document_text,
)
from .multi import MultiSiteSearchEngine, discover_sites, filter_sites

__all__ = [
    'SearchEngine',
    'EnhancedSearchEngine',
    'SearchCache',
    'parse_query',
    'group_results_by_section',
    'compute_index_fingerprint',
    'document_has_phrases',
    'find_phrase_positions',
    'highlight_terms',
    'find_best_snippet',
    'check_phrase_match',
    'normalize_document_text',
    'MultiSiteSearchEngine',
    'discover_sites',
    'filter_sites',
]
