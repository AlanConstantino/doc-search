"""Compatibility shim. Prefer ``doc_search.crawl``."""

from ..crawl import *  # noqa: F401,F403
from ..crawl import (
    Crawler, Fetcher, FetchResult, RateLimiter, UrlFilter, PageProcessor,
    SKIP_EXTENSIONS, EXTRACTABLE_DOC_EXTENSIONS, SKIP_PATH_PATTERNS,
    is_skippable_extension, is_extractable_doc, is_skippable_path,
    is_under_base_path, content_hash, build_page_data, build_document_data,
)

__all__ = [
    'Crawler', 'Fetcher', 'FetchResult', 'RateLimiter', 'UrlFilter',
    'PageProcessor', 'SKIP_EXTENSIONS', 'EXTRACTABLE_DOC_EXTENSIONS',
    'SKIP_PATH_PATTERNS', 'is_skippable_extension', 'is_extractable_doc',
    'is_skippable_path', 'is_under_base_path', 'content_hash',
    'build_page_data', 'build_document_data',
]
