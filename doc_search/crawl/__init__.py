"""Crawl layer: fetch, filter, persist pages.

Depends on ``core`` and ``extract`` only.
"""

from .crawler import Crawler
from .fetcher import Fetcher, FetchResult
from .rate_limiter import RateLimiter
from .robots import RobotsChecker
from .state import CrawlState, CrawlError
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

__all__ = [
    'Crawler',
    'Fetcher',
    'FetchResult',
    'RateLimiter',
    'RobotsChecker',
    'CrawlState',
    'CrawlError',
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
