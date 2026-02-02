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
    
    def test_skips_visited_urls(self):
        """Should skip already visited URLs."""
        crawler = self.create_crawler()
        crawler.state.mark_visited('https://example.com/page1')
        
        self.assertFalse(crawler._should_crawl('https://example.com/page1'))
    
    def test_allows_unvisited_urls(self):
        """Should allow unvisited URLs."""
        crawler = self.create_crawler()
        
        # Mock robots.txt to allow all
        crawler.robots.can_fetch = Mock(return_value=True)
        
        self.assertTrue(crawler._should_crawl('https://example.com/page1'))


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
