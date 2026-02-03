"""
Crawler package for doc-search.

Re-exports Crawler from _crawler for backward compatibility.
"""

from ._crawler import Crawler
from .fetcher import Fetcher, FetchResult
from .url_filter import (
    SKIP_EXTENSIONS,
    EXTRACTABLE_DOC_EXTENSIONS,
    SKIP_PATH_PATTERNS,
    UrlFilter,
    is_skippable_extension,
    is_extractable_doc,
    is_skippable_path,
    is_under_base_path,
)
from ..rate_limiter import RateLimiter

__all__ = [
    'Crawler',
    'Fetcher',
    'FetchResult',
    'RateLimiter',
    'UrlFilter',
    'SKIP_EXTENSIONS',
    'EXTRACTABLE_DOC_EXTENSIONS',
    'SKIP_PATH_PATTERNS',
    'is_skippable_extension',
    'is_extractable_doc',
    'is_skippable_path',
    'is_under_base_path',
]
