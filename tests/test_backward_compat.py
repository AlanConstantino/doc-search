"""
Test backward compatibility for public API imports.

Phase 6.5: Ensures all public imports from the pre-refactor API
continue to work after the crawler module reorganization.
"""

import pytest


class TestCrawlerBackwardCompatibility:
    """Test that crawler module exports maintain backward compatibility."""

    def test_crawler_import(self):
        """Verify Crawler can be imported from doc_search.crawler."""
        from doc_search.crawler import Crawler
        assert Crawler is not None

    def test_rate_limiter_import(self):
        """Verify RateLimiter can be imported from doc_search.crawler."""
        from doc_search.crawler import RateLimiter
        assert RateLimiter is not None

    def test_fetcher_import(self):
        """Verify Fetcher can be imported from doc_search.crawler."""
        from doc_search.crawler import Fetcher, FetchResult
        assert Fetcher is not None
        assert FetchResult is not None

    def test_url_filter_import(self):
        """Verify UrlFilter and helpers can be imported from doc_search.crawler."""
        from doc_search.crawler import (
            UrlFilter,
            SKIP_EXTENSIONS,
            EXTRACTABLE_DOC_EXTENSIONS,
            SKIP_PATH_PATTERNS,
            is_skippable_extension,
            is_extractable_doc,
            is_skippable_path,
            is_under_base_path,
        )
        assert UrlFilter is not None
        assert isinstance(SKIP_EXTENSIONS, frozenset)
        assert isinstance(EXTRACTABLE_DOC_EXTENSIONS, frozenset)
        assert isinstance(SKIP_PATH_PATTERNS, (tuple, list))
        assert callable(is_skippable_extension)
        assert callable(is_extractable_doc)
        assert callable(is_skippable_path)
        assert callable(is_under_base_path)

    def test_processor_import(self):
        """Verify PageProcessor and helpers can be imported from doc_search.crawler."""
        from doc_search.crawler import (
            PageProcessor,
            content_hash,
            build_page_data,
            build_document_data,
        )
        assert PageProcessor is not None
        assert callable(content_hash)
        assert callable(build_page_data)
        assert callable(build_document_data)

    def test_all_exports_present(self):
        """Verify __all__ contains expected exports."""
        from doc_search import crawler
        
        expected_exports = [
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
        
        for name in expected_exports:
            assert name in crawler.__all__, f"{name} not in crawler.__all__"
            assert hasattr(crawler, name), f"{name} not accessible on crawler module"


class TestRateLimiterBackwardCompatibility:
    """Test RateLimiter from its canonical location."""

    def test_rate_limiter_direct_import(self):
        """Verify RateLimiter can be imported from doc_search.rate_limiter."""
        from doc_search.rate_limiter import RateLimiter
        assert RateLimiter is not None

    def test_rate_limiter_instantiation(self):
        """Verify RateLimiter can be instantiated."""
        from doc_search.rate_limiter import RateLimiter
        rl = RateLimiter(default_delay=0.5)
        assert rl is not None
