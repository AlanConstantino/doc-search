"""Compatibility shim. Prefer ``doc_search.search.snippets`` / ``app.cli.formatters``."""

from .search.snippets import (
    highlight_terms, find_best_snippet, check_phrase_match, normalize_document_text,
    _compile_terms_pattern,
)
from .app.cli.formatters import format_results, highlight_terms_ansi

__all__ = [
    'highlight_terms', 'highlight_terms_ansi', 'find_best_snippet',
    'check_phrase_match', 'normalize_document_text', 'format_results',
]
