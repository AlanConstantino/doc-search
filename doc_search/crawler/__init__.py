"""
Crawler package for doc-search.

This package provides the web crawling functionality for doc-search.
It has been refactored from a single file into a modular package while
maintaining full backward compatibility.

Public API (all importable from doc_search.crawler):
    - Crawler: Main crawler class for crawling documentation sites
    - RateLimiter: Rate limiting for HTTP requests (re-exported from rate_limiter)
    - Fetcher: HTTP fetching with retry logic
    - FetchResult: Dataclass for fetch results
    - UrlFilter: URL validation and filtering
    - PageProcessor: Content processing and extraction

Backward-compatible imports:
    >>> from doc_search.crawler import Crawler
    >>> from doc_search.crawler import RateLimiter
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
from .processor import (
    PageProcessor,
    content_hash,
    build_page_data,
    build_document_data,
)
from ..rate_limiter import RateLimiter

__all__ = [
    'Crawler',
    'Fetcher',
    'FetchResult',
    'RateLimiter',
    'UrlFilter',
    'PageProcessor',
    'SKIP_EXTENSIONS',
    'EXTRACTABLE_DOC_EXTENSIONS',
    'SKIP_PATH_PATTERNS',
    'is_skippable_extension',
    'is_extractable_doc',
    'is_skippable_path',
    'is_under_base_path',
    'content_hash',
    'build_page_data',
    'build_document_data',
]
