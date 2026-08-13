"""Compatibility shim. Prefer ``doc_search.core`` and ``doc_search.app.terminal``."""

from .core.http import create_permissive_ssl_context, make_basic_auth_header
from .core.urls import (
    normalize_url, get_domain, is_same_domain, hash_string, url_to_filename,
    site_hash, resolve_url, sanitize_url, is_valid_url, is_html_content,
)
from .core.text import (
    STOP_WORDS, tokenize, tokenize_phrase, tokenize_with_exact,
    format_size, format_duration,
)
from .core.stemmer import stem
from .app.terminal import (
    Colors, colorize, emoji, highlight_match,
    style_title, style_url, style_score, style_number,
    style_info, style_success, style_error,
    _resolve_styles, _load_color_theme, _parse_color_value,
)

__all__ = [
    'create_permissive_ssl_context', 'make_basic_auth_header',
    'normalize_url', 'get_domain', 'is_same_domain', 'hash_string',
    'url_to_filename', 'site_hash', 'resolve_url', 'sanitize_url',
    'is_valid_url', 'is_html_content',
    'STOP_WORDS', 'tokenize', 'tokenize_phrase', 'tokenize_with_exact',
    'format_size', 'format_duration', 'stem',
    'Colors', 'colorize', 'emoji', 'highlight_match',
    'style_title', 'style_url', 'style_score', 'style_number',
    'style_info', 'style_success', 'style_error',
]
