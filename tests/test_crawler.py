"""
Tests for the web crawler module.
"""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import Mock, patch, MagicMock
from urllib.error import URLError, HTTPError
from http.client import HTTPMessage
from io import BytesIO

from doc_search.crawler import Crawler, CrawlState, RateLimiter


# ============================================================================
# Test Fixtures
# ============================================================================

# Mock HTML responses for testing
MOCK_HTML_RESPONSES: Dict[str, str] = {
    'https://example.com/': '''
        <!DOCTYPE html>
        <html>
        <head><title>Example Home</title></head>
        <body>
            <h1>Welcome to Example</h1>
            <p>This is the homepage.</p>
            <a href="/page1">Page 1</a>
            <a href="/page2">Page 2</a>
            <a href="https://external.com/link">External Link</a>
        </body>
        </html>
    ''',
    'https://example.com/page1': '''
        <!DOCTYPE html>
        <html>
        <head><title>Page 1</title></head>
        <body>
            <h1>Page 1</h1>
            <p>Content of page 1.</p>
            <a href="/">Home</a>
            <a href="/page1/subpage">Subpage</a>
        </body>
        </html>
    ''',
    'https://example.com/page2': '''
        <!DOCTYPE html>
        <html>
        <head><title>Page 2</title></head>
        <body>
            <h1>Page 2</h1>
            <p>Content of page 2.</p>
            <a href="/">Home</a>
        </body>
        </html>
    ''',
    'https://example.com/page1/subpage': '''
        <!DOCTYPE html>
        <html>
        <head><title>Subpage</title></head>
        <body>
            <h1>Subpage</h1>
            <p>This is a subpage under page1.</p>
        </body>
        </html>
    ''',
    'https://example.com/docs/': '''
        <!DOCTYPE html>
        <html>
        <head><title>Docs Home</title></head>
        <body>
            <h1>Documentation</h1>
            <a href="/docs/getting-started">Getting Started</a>
            <a href="/docs/api">API Reference</a>
            <a href="/other">Other Section</a>
        </body>
        </html>
    ''',
    'https://example.com/docs/getting-started': '''
        <!DOCTYPE html>
        <html>
        <head><title>Getting Started</title></head>
        <body>
            <h1>Getting Started</h1>
            <p>How to get started with our docs.</p>
        </body>
        </html>
    ''',
    'https://example.com/docs/api': '''
        <!DOCTYPE html>
        <html>
        <head><title>API Reference</title></head>
        <body>
            <h1>API Reference</h1>
            <p>Complete API documentation.</p>
        </body>
        </html>
    ''',
}


def create_mock_response(content: str, status: int = 200, 
                        content_type: str = 'text/html; charset=utf-8',
                        etag: Optional[str] = None,
                        last_modified: Optional[str] = None):
    """Create a mock HTTP response object."""
    mock_response = MagicMock()
    mock_response.read.return_value = content.encode('utf-8')
    mock_response.status = status
    mock_response.code = status
    
    # Create headers dict-like object
    headers = {
        'Content-Type': content_type,
        'Content-Encoding': '',
    }
    if etag:
        headers['ETag'] = etag
    if last_modified:
        headers['Last-Modified'] = last_modified
    
    mock_response.headers = MagicMock()
    mock_response.headers.get = lambda key, default='': headers.get(key, default)
    
    return mock_response


def mock_urlopen_factory(responses: Dict[str, str] = None):
    """
    Create a mock urlopen function that returns content from a dict.
    
    Args:
        responses: Dict mapping URLs to HTML content. If None, uses MOCK_HTML_RESPONSES.
    """
    if responses is None:
        responses = MOCK_HTML_RESPONSES
    
    def mock_urlopen(request, timeout=None, context=None):
        url = request.full_url if hasattr(request, 'full_url') else str(request)
        
        # Normalize URL (remove trailing slash for matching)
        normalized = url.rstrip('/')
        
        # Try exact match first
        if url in responses:
            return create_mock_response(responses[url])
        
        # Try normalized match
        if normalized in responses:
            return create_mock_response(responses[normalized])
        
        # Try with trailing slash
        if normalized + '/' in responses:
            return create_mock_response(responses[normalized + '/'])
        
        # URL not found - return 404
        raise HTTPError(url, 404, 'Not Found', {}, None)
    
    return mock_urlopen


class CrawlerTestCase(unittest.TestCase):
    """Base test case with common setup for crawler tests."""
    
    def setUp(self):
        """Create temporary directory for crawl data."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
        
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_crawler(self, base_url: str = 'https://example.com/', 
                       **kwargs) -> Crawler:
        """
        Create a Crawler instance for testing.
        
        Args:
            base_url: Starting URL for the crawler
            **kwargs: Additional arguments passed to Crawler
            
        Returns:
            Configured Crawler instance
        """
        defaults = {
            'data_dir': self.data_dir,
            'delay': 0.0,  # No delay in tests
            'timeout': 5.0,
            'verbose': False,
            'workers': 1,
        }
        defaults.update(kwargs)
        
        crawler = Crawler(base_url, **defaults)
        return crawler
    
    def create_crawl_state(self, filename: str = 'crawl_state.json') -> CrawlState:
        """Create a CrawlState instance for testing."""
        state_file = self.data_dir / filename
        return CrawlState(state_file)


# ============================================================================
# CrawlState Tests
# ============================================================================

class TestCrawlState(CrawlerTestCase):
    """Tests for CrawlState persistence and thread safety."""
    
    def test_initial_state_empty(self):
        """New CrawlState should have empty collections."""
        state = self.create_crawl_state()
        
        self.assertEqual(len(state.visited), 0)
        self.assertEqual(len(state.pending), 0)
        self.assertEqual(len(state.failed), 0)
        self.assertEqual(state.stats['pages_crawled'], 0)
    
    def test_mark_visited(self):
        """Should track visited URLs."""
        state = self.create_crawl_state()
        
        state.mark_visited('https://example.com/page1')
        self.assertTrue(state.is_visited('https://example.com/page1'))
        self.assertFalse(state.is_visited('https://example.com/page2'))
    
    def test_add_and_pop_urls(self):
        """Should add and pop URLs from queue."""
        state = self.create_crawl_state()
        
        state.add_urls([
            ('https://example.com/page1', 0),
            ('https://example.com/page2', 1),
        ])
        
        item = state.pop_url()
        self.assertEqual(item, ('https://example.com/page1', 0))
        
        item = state.pop_url()
        self.assertEqual(item, ('https://example.com/page2', 1))
        
        item = state.pop_url()
        self.assertIsNone(item)
    
    def test_pop_url_returns_none_when_empty(self):
        """pop_url should return None when queue is empty."""
        state = self.create_crawl_state()
        self.assertIsNone(state.pop_url())


# ============================================================================
# RateLimiter Tests
# ============================================================================

class TestRateLimiter(CrawlerTestCase):
    """Tests for RateLimiter class."""
    
    def test_default_delay(self):
        """Should use default delay for unknown domains."""
        limiter = RateLimiter(default_delay=0.5)
        self.assertEqual(limiter.get_delay('example.com'), 0.5)
    
    def test_custom_domain_delay(self):
        """Should use custom delay for specific domains."""
        limiter = RateLimiter(default_delay=0.5)
        limiter.set_domain_delay('slow.example.com', 2.0)
        
        self.assertEqual(limiter.get_delay('slow.example.com'), 2.0)
        self.assertEqual(limiter.get_delay('other.com'), 0.5)


# ============================================================================
# Crawler URL Filtering Tests  
# ============================================================================

class TestCrawlerURLFiltering(CrawlerTestCase):
    """Tests for Crawler._should_crawl() URL filtering logic."""
    
    def setUp(self):
        """Set up test fixtures."""
        super().setUp()
        # Create a crawler and mock robots.txt to allow all by default
        self.crawler = self.create_crawler()
        self.crawler.robots.can_fetch = Mock(return_value=True)
    
    # -------------------------------------------------------------------------
    # Already-visited URL tests
    # -------------------------------------------------------------------------
    
    def test_skips_visited_urls(self):
        """Should skip already visited URLs."""
        self.crawler.state.mark_visited('https://example.com/page1')
        self.assertFalse(self.crawler._should_crawl('https://example.com/page1'))
    
    def test_allows_unvisited_urls(self):
        """Should allow unvisited URLs."""
        self.assertTrue(self.crawler._should_crawl('https://example.com/page1'))
    
    # -------------------------------------------------------------------------
    # Non-HTML extension tests
    # -------------------------------------------------------------------------
    
    def test_skips_zip_extension(self):
        """Should skip .zip files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/file.zip'))
    
    def test_skips_tar_gz_extension(self):
        """Should skip .tar.gz files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/file.tar.gz'))
    
    def test_skips_png_extension(self):
        """Should skip .png image files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/image.png'))
    
    def test_skips_jpg_extension(self):
        """Should skip .jpg image files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/photo.jpg'))
    
    def test_skips_jpeg_extension(self):
        """Should skip .jpeg image files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/photo.jpeg'))
    
    def test_skips_gif_extension(self):
        """Should skip .gif image files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/animation.gif'))
    
    def test_skips_mp4_extension(self):
        """Should skip .mp4 video files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/video.mp4'))
    
    def test_skips_css_extension(self):
        """Should skip .css files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/styles.css'))
    
    def test_skips_js_extension(self):
        """Should skip .js files."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/script.js'))
    
    def test_skips_pdf_without_extract_docs(self):
        """Should skip .pdf files when extract_docs is disabled."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/document.pdf'))
    
    def test_allows_pdf_with_extract_docs(self):
        """Should allow .pdf files when extract_docs is enabled."""
        crawler = self.create_crawler(extract_docs=True)
        crawler.robots.can_fetch = Mock(return_value=True)
        self.assertTrue(crawler._should_crawl('https://example.com/document.pdf'))
    
    def test_allows_html_extension(self):
        """Should allow .html files."""
        self.assertTrue(self.crawler._should_crawl('https://example.com/page.html'))
    
    def test_allows_htm_extension(self):
        """Should allow .htm files."""
        self.assertTrue(self.crawler._should_crawl('https://example.com/page.htm'))
    
    def test_allows_no_extension(self):
        """Should allow URLs without file extensions."""
        self.assertTrue(self.crawler._should_crawl('https://example.com/page'))
    
    def test_allows_trailing_slash(self):
        """Should allow URLs with trailing slash (directories)."""
        self.assertTrue(self.crawler._should_crawl('https://example.com/docs/'))
    
    # -------------------------------------------------------------------------
    # Max depth tests
    # -------------------------------------------------------------------------
    
    def test_allows_within_max_depth(self):
        """Should allow URLs within max_depth limit."""
        crawler = self.create_crawler(max_depth=2)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/page', depth=0))
        self.assertTrue(crawler._should_crawl('https://example.com/page', depth=1))
        self.assertTrue(crawler._should_crawl('https://example.com/page', depth=2))
    
    def test_skips_beyond_max_depth(self):
        """Should skip URLs beyond max_depth limit."""
        crawler = self.create_crawler(max_depth=2)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertFalse(crawler._should_crawl('https://example.com/page', depth=3))
        self.assertFalse(crawler._should_crawl('https://example.com/page', depth=10))
    
    def test_no_max_depth_allows_any_depth(self):
        """Should allow any depth when max_depth is None."""
        crawler = self.create_crawler(max_depth=None)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/page', depth=100))
    
    def test_max_depth_zero_only_allows_start(self):
        """max_depth=0 should only allow the starting page."""
        crawler = self.create_crawler(max_depth=0)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/page', depth=0))
        self.assertFalse(crawler._should_crawl('https://example.com/page', depth=1))
    
    # -------------------------------------------------------------------------
    # Same path restriction tests
    # -------------------------------------------------------------------------
    
    def test_same_path_allows_under_base_path(self):
        """Should allow URLs under the base path when same_path=True."""
        crawler = self.create_crawler(
            base_url='https://example.com/docs/',
            same_path=True
        )
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/docs/'))
        self.assertTrue(crawler._should_crawl('https://example.com/docs/api'))
        self.assertTrue(crawler._should_crawl('https://example.com/docs/guide/intro'))
    
    def test_same_path_skips_outside_base_path(self):
        """Should skip URLs outside the base path when same_path=True."""
        crawler = self.create_crawler(
            base_url='https://example.com/docs/',
            same_path=True
        )
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertFalse(crawler._should_crawl('https://example.com/other'))
        self.assertFalse(crawler._should_crawl('https://example.com/'))
        self.assertFalse(crawler._should_crawl('https://example.com/blog/post'))
    
    def test_same_path_false_allows_any_path(self):
        """Should allow any path when same_path=False."""
        crawler = self.create_crawler(
            base_url='https://example.com/docs/',
            same_path=False
        )
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/other'))
        self.assertTrue(crawler._should_crawl('https://example.com/'))
    
    def test_same_path_handles_trailing_slashes(self):
        """Should handle trailing slashes correctly in path matching."""
        crawler = self.create_crawler(
            base_url='https://example.com/docs',  # No trailing slash
            same_path=True
        )
        crawler.robots.can_fetch = Mock(return_value=True)
        
        # Both with and without trailing slash should work
        self.assertTrue(crawler._should_crawl('https://example.com/docs'))
        self.assertTrue(crawler._should_crawl('https://example.com/docs/'))
        self.assertTrue(crawler._should_crawl('https://example.com/docs/api'))
    
    def test_same_path_root_allows_all(self):
        """Root path with same_path should allow entire domain."""
        crawler = self.create_crawler(
            base_url='https://example.com/',
            same_path=True
        )
        crawler.robots.can_fetch = Mock(return_value=True)
        
        # Root path should disable same_path restriction
        self.assertTrue(crawler._should_crawl('https://example.com/anything'))
        self.assertTrue(crawler._should_crawl('https://example.com/deep/nested/path'))
    
    # -------------------------------------------------------------------------
    # Stay on domain tests
    # -------------------------------------------------------------------------
    
    def test_stay_on_domain_allows_same_domain(self):
        """Should allow URLs on the same domain when stay_on_domain=True."""
        crawler = self.create_crawler(stay_on_domain=True)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/page'))
        self.assertTrue(crawler._should_crawl('https://example.com/other/path'))
    
    def test_stay_on_domain_skips_external_domain(self):
        """Should skip URLs on external domains when stay_on_domain=True."""
        crawler = self.create_crawler(stay_on_domain=True)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertFalse(crawler._should_crawl('https://other.com/page'))
        self.assertFalse(crawler._should_crawl('https://external.example.org/'))
    
    def test_stay_on_domain_skips_subdomain(self):
        """Should skip URLs on different subdomains when stay_on_domain=True."""
        crawler = self.create_crawler(
            base_url='https://example.com/',
            stay_on_domain=True
        )
        crawler.robots.can_fetch = Mock(return_value=True)
        
        # Subdomains are different domains
        self.assertFalse(crawler._should_crawl('https://sub.example.com/page'))
        self.assertFalse(crawler._should_crawl('https://blog.example.com/'))
    
    def test_stay_on_domain_false_allows_external(self):
        """Should allow external domains when stay_on_domain=False."""
        crawler = self.create_crawler(stay_on_domain=False)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://other.com/page'))
    
    # -------------------------------------------------------------------------
    # Download/archive path tests
    # -------------------------------------------------------------------------
    
    def test_skips_download_path(self):
        """Should skip URLs with /download/ in path."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/download/file'))
        self.assertFalse(self.crawler._should_crawl('https://example.com/downloads/archive'))
    
    def test_skips_archive_path(self):
        """Should skip URLs with /archive/ in path."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/archive/old'))
        self.assertFalse(self.crawler._should_crawl('https://example.com/archives/2020'))
    
    def test_skips_releases_path(self):
        """Should skip URLs with /releases/ in path."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/releases/v1.0'))
        self.assertFalse(self.crawler._should_crawl('https://example.com/release/latest'))
    
    def test_skips_dist_path(self):
        """Should skip URLs with /dist/ in path."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/dist/package.tar.gz'))
    
    def test_skips_packages_path(self):
        """Should skip URLs with /packages/ in path."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/packages/mylib'))
    
    def test_allows_normal_doc_paths(self):
        """Should allow normal documentation paths."""
        self.assertTrue(self.crawler._should_crawl('https://example.com/docs/api'))
        self.assertTrue(self.crawler._should_crawl('https://example.com/guide/intro'))
        self.assertTrue(self.crawler._should_crawl('https://example.com/reference/classes'))
    
    # -------------------------------------------------------------------------
    # Robots.txt compliance tests
    # -------------------------------------------------------------------------
    
    def test_respects_robots_disallow(self):
        """Should skip URLs disallowed by robots.txt."""
        self.crawler.robots.can_fetch = Mock(return_value=False)
        self.assertFalse(self.crawler._should_crawl('https://example.com/private'))
    
    def test_allows_robots_allow(self):
        """Should allow URLs allowed by robots.txt."""
        self.crawler.robots.can_fetch = Mock(return_value=True)
        self.assertTrue(self.crawler._should_crawl('https://example.com/public'))
    
    # -------------------------------------------------------------------------
    # Custom URL filter tests
    # -------------------------------------------------------------------------
    
    def test_custom_filter_blocks_url(self):
        """Should respect custom url_filter returning False."""
        def block_admin(url):
            return '/admin/' not in url
        
        crawler = self.create_crawler(url_filter=block_admin)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertFalse(crawler._should_crawl('https://example.com/admin/panel'))
        self.assertTrue(crawler._should_crawl('https://example.com/docs/'))
    
    def test_custom_filter_allows_url(self):
        """Should respect custom url_filter returning True."""
        def allow_all(url):
            return True
        
        crawler = self.create_crawler(url_filter=allow_all)
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/anything'))
    
    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------
    
    def test_empty_path(self):
        """Should handle URLs with empty path."""
        self.assertTrue(self.crawler._should_crawl('https://example.com'))
    
    def test_root_path(self):
        """Should handle root path URL."""
        self.assertTrue(self.crawler._should_crawl('https://example.com/'))
    
    def test_case_insensitive_extension(self):
        """Should handle extensions case-insensitively."""
        self.assertFalse(self.crawler._should_crawl('https://example.com/image.PNG'))
        self.assertFalse(self.crawler._should_crawl('https://example.com/file.ZIP'))
        self.assertFalse(self.crawler._should_crawl('https://example.com/video.MP4'))


# ============================================================================
# Placeholder for Additional Tests
# ============================================================================

class TestCrawlerPlaceholder(CrawlerTestCase):
    """Placeholder tests - to be expanded in subsequent issues."""
    
    def test_crawler_instantiation(self):
        """Crawler should instantiate without errors."""
        crawler = self.create_crawler()
        
        self.assertEqual(crawler.base_url, 'https://example.com/')
        self.assertEqual(crawler.delay, 0.0)
        self.assertFalse(crawler.verbose)


if __name__ == '__main__':
    unittest.main()
