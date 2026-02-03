"""
Crawler package for doc-search.

Re-exports Crawler from _crawler for backward compatibility.
"""

from ._crawler import (
    Crawler,
    SKIP_EXTENSIONS,
    EXTRACTABLE_DOC_EXTENSIONS,
    SKIP_PATH_PATTERNS,
)
from .fetcher import Fetcher, FetchResult
from ..rate_limiter import RateLimiter

__all__ = [
    'Crawler',
    'Fetcher',
    'FetchResult',
    'RateLimiter',
    'SKIP_EXTENSIONS',
    'EXTRACTABLE_DOC_EXTENSIONS',
    'SKIP_PATH_PATTERNS',
]
