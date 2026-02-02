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

from doc_search.crawler import Crawler, RateLimiter
from doc_search.crawl_state import CrawlState, CrawlError


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
    
    # -------------------------------------------------------------------------
    # Basic operations tests
    # -------------------------------------------------------------------------
    
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
    
    def test_add_urls_skips_visited(self):
        """add_urls should skip URLs that are already visited."""
        state = self.create_crawl_state()
        state.mark_visited('https://example.com/page1')
        
        state.add_urls([
            ('https://example.com/page1', 0),  # Already visited
            ('https://example.com/page2', 0),  # New
        ])
        
        # Only page2 should be in the queue
        item = state.pop_url()
        self.assertEqual(item, ('https://example.com/page2', 0))
        self.assertIsNone(state.pop_url())
    
    def test_add_urls_skips_duplicates_in_pending(self):
        """add_urls should skip URLs already in the pending queue."""
        state = self.create_crawl_state()
        
        state.add_urls([('https://example.com/page1', 0)])
        state.add_urls([
            ('https://example.com/page1', 1),  # Same URL, different depth
            ('https://example.com/page2', 0),  # New URL
        ])
        
        # Should have page1 at depth 0, then page2 at depth 0
        self.assertEqual(state.pop_url(), ('https://example.com/page1', 0))
        self.assertEqual(state.pop_url(), ('https://example.com/page2', 0))
        self.assertIsNone(state.pop_url())
    
    def test_increment_stat(self):
        """Should increment stat counters correctly."""
        state = self.create_crawl_state()
        
        state.increment_stat('pages_crawled')
        state.increment_stat('pages_crawled')
        state.increment_stat('pages_crawled', 5)
        
        self.assertEqual(state.stats['pages_crawled'], 7)
    
    def test_mark_failed_increments_retry_count(self):
        """mark_failed should increment retry count and re-queue URL."""
        state = self.create_crawl_state()
        
        # First failure - should return True (will retry)
        result = state.mark_failed('https://example.com/error', 1)
        self.assertTrue(result)
        self.assertEqual(state.failed['https://example.com/error'], 1)
        
        # Second failure
        state.pop_url()  # Remove from queue
        result = state.mark_failed('https://example.com/error', 1)
        self.assertTrue(result)
        self.assertEqual(state.failed['https://example.com/error'], 2)
        
        # Third failure
        state.pop_url()
        result = state.mark_failed('https://example.com/error', 1)
        self.assertTrue(result)
        self.assertEqual(state.failed['https://example.com/error'], 3)
        
        # Fourth failure - exceeded max retries, should return False
        state.pop_url()
        result = state.mark_failed('https://example.com/error', 1)
        self.assertFalse(result)
        self.assertEqual(state.stats['pages_failed'], 1)
    
    def test_clear_resets_all_state(self):
        """clear() should reset all state."""
        state = self.create_crawl_state()
        
        # Add some state
        state.mark_visited('https://example.com/page1')
        state.add_urls([('https://example.com/page2', 0)])
        state.increment_stat('pages_crawled', 5)
        state.save()
        
        # Clear
        state.clear()
        
        self.assertEqual(len(state.visited), 0)
        self.assertEqual(len(state.pending), 0)
        self.assertEqual(state.stats['pages_crawled'], 0)
        self.assertFalse(state.state_file.exists())
    
    def test_get_progress(self):
        """get_progress should return formatted progress string."""
        state = self.create_crawl_state()
        
        state.increment_stat('pages_crawled', 5)
        # Add 10 unique URLs
        state.add_urls([(f'https://example.com/page{i}', 0) for i in range(10)])
        
        progress = state.get_progress()
        self.assertIn('[5/', progress)
        self.assertIn('queue: 10', progress)
        
        # With max_pages
        progress = state.get_progress(max_pages=100)
        self.assertIn('[5/100]', progress)
    
    # -------------------------------------------------------------------------
    # Persistence tests
    # -------------------------------------------------------------------------
    
    def test_save_creates_json_file(self):
        """save() should create a valid JSON file."""
        state = self.create_crawl_state()
        
        state.mark_visited('https://example.com/page1')
        state.add_urls([('https://example.com/page2', 1)])
        state.increment_stat('pages_crawled', 3)
        
        state.save()
        
        # Verify file exists and is valid JSON
        self.assertTrue(state.state_file.exists())
        
        with open(state.state_file) as f:
            data = json.load(f)
        
        self.assertIn('visited', data)
        self.assertIn('pending', data)
        self.assertIn('stats', data)
        self.assertIn('https://example.com/page1', data['visited'])
        self.assertEqual(data['stats']['pages_crawled'], 3)
    
    def test_load_restores_state(self):
        """load() should restore state correctly."""
        state1 = self.create_crawl_state()
        
        # Set up state
        state1.mark_visited('https://example.com/visited')
        state1.add_urls([
            ('https://example.com/pending1', 0),
            ('https://example.com/pending2', 1),
        ])
        state1.increment_stat('pages_crawled', 5)
        state1.increment_stat('bytes_downloaded', 1024)
        state1.save()
        
        # Create new state instance and load
        state2 = self.create_crawl_state()
        result = state2.load()
        
        self.assertTrue(result)
        self.assertTrue(state2.is_visited('https://example.com/visited'))
        self.assertEqual(state2.stats['pages_crawled'], 5)
        self.assertEqual(state2.stats['bytes_downloaded'], 1024)
        
        # Check pending queue
        item = state2.pop_url()
        self.assertEqual(item, ('https://example.com/pending1', 0))
        item = state2.pop_url()
        self.assertEqual(item, ('https://example.com/pending2', 1))
    
    def test_load_handles_missing_file(self):
        """load() should handle missing state file gracefully."""
        state = self.create_crawl_state()
        
        result = state.load()
        
        self.assertFalse(result)
        # State should remain empty
        self.assertEqual(len(state.visited), 0)
        self.assertEqual(len(state.pending), 0)
    
    def test_load_handles_corrupted_json(self):
        """load() should handle corrupted JSON gracefully."""
        state = self.create_crawl_state()
        
        # Create corrupted JSON file
        with open(state.state_file, 'w') as f:
            f.write('{ invalid json content }}}')
        
        result = state.load()
        
        self.assertFalse(result)
        # State should remain empty
        self.assertEqual(len(state.visited), 0)
    
    def test_load_handles_empty_file(self):
        """load() should handle empty file gracefully."""
        state = self.create_crawl_state()
        
        # Create empty file
        state.state_file.touch()
        
        result = state.load()
        
        self.assertFalse(result)
    
    def test_load_handles_partial_data(self):
        """load() should handle partial/missing fields gracefully."""
        state = self.create_crawl_state()
        
        # Create JSON with missing fields
        with open(state.state_file, 'w') as f:
            json.dump({'visited': ['https://example.com/']}, f)
        
        result = state.load()
        
        self.assertTrue(result)
        self.assertTrue(state.is_visited('https://example.com/'))
        # Other fields should have defaults
        self.assertEqual(len(state.pending), 0)
    
    def test_save_is_atomic(self):
        """save() should write atomically (via temp file)."""
        state = self.create_crawl_state()
        
        state.mark_visited('https://example.com/')
        state.save()
        
        # Verify no .tmp file remains
        tmp_file = state.state_file.with_suffix('.tmp')
        self.assertFalse(tmp_file.exists())
        self.assertTrue(state.state_file.exists())
    
    def test_round_trip_preserves_all_data(self):
        """Save → load should preserve all data exactly."""
        state1 = self.create_crawl_state()
        
        # Set up complex state
        visited_urls = [f'https://example.com/page{i}' for i in range(5)]
        for url in visited_urls:
            state1.mark_visited(url)
        
        pending_urls = [(f'https://example.com/new{i}', i % 3) for i in range(3)]
        state1.add_urls(pending_urls)
        
        state1.failed['https://example.com/error'] = 2
        state1.stats['pages_crawled'] = 10
        state1.stats['pages_failed'] = 1
        state1.stats['bytes_downloaded'] = 50000
        
        state1.save()
        
        # Load into new instance
        state2 = self.create_crawl_state()
        state2.load()
        
        # Verify all data matches
        for url in visited_urls:
            self.assertTrue(state2.is_visited(url))
        
        self.assertEqual(state2.stats['pages_crawled'], 10)
        self.assertEqual(state2.stats['pages_failed'], 1)
        self.assertEqual(state2.stats['bytes_downloaded'], 50000)
        self.assertEqual(state2.failed.get('https://example.com/error'), 2)
    
    # -------------------------------------------------------------------------
    # Thread safety tests
    # -------------------------------------------------------------------------
    
    def test_mark_visited_is_thread_safe(self):
        """mark_visited should be thread-safe under concurrent access."""
        state = self.create_crawl_state()
        errors = []
        
        def mark_many(start):
            try:
                for i in range(100):
                    state.mark_visited(f'https://example.com/page{start}_{i}')
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=mark_many, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        # Should have 500 visited URLs (5 threads × 100 URLs each)
        self.assertEqual(len(state.visited), 500)
    
    def test_pop_url_is_thread_safe(self):
        """pop_url should be thread-safe under concurrent access."""
        state = self.create_crawl_state()
        
        # Add 1000 URLs
        urls = [(f'https://example.com/page{i}', 0) for i in range(1000)]
        state.add_urls(urls)
        
        popped_urls = []
        lock = threading.Lock()
        errors = []
        
        def pop_many():
            try:
                while True:
                    item = state.pop_url()
                    if item is None:
                        break
                    with lock:
                        popped_urls.append(item)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=pop_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        # All 1000 URLs should have been popped exactly once
        self.assertEqual(len(popped_urls), 1000)
        # No duplicates
        popped_set = set(url for url, _ in popped_urls)
        self.assertEqual(len(popped_set), 1000)
    
    def test_concurrent_add_and_pop(self):
        """Should handle concurrent add and pop operations safely."""
        state = self.create_crawl_state()
        errors = []
        
        # Seed with some URLs
        initial_urls = [(f'https://example.com/seed{i}', 0) for i in range(100)]
        state.add_urls(initial_urls)
        
        def add_urls(start):
            try:
                for i in range(50):
                    state.add_urls([(f'https://example.com/added{start}_{i}', 0)])
                    time.sleep(0.001)  # Small delay to interleave
            except Exception as e:
                errors.append(e)
        
        def pop_urls():
            try:
                for _ in range(50):
                    state.pop_url()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(3):
            threads.append(threading.Thread(target=add_urls, args=(i,)))
            threads.append(threading.Thread(target=pop_urls))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
    
    def test_increment_stat_is_thread_safe(self):
        """increment_stat should be thread-safe under concurrent access."""
        state = self.create_crawl_state()
        errors = []
        
        def increment_many():
            try:
                for _ in range(100):
                    state.increment_stat('pages_crawled')
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=increment_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        self.assertEqual(state.stats['pages_crawled'], 1000)
    
    # -------------------------------------------------------------------------
    # Error tracking tests
    # -------------------------------------------------------------------------
    
    def test_record_error(self):
        """record_error should add a CrawlError to the errors list."""
        state = self.create_crawl_state()
        
        state.record_error(
            url='https://example.com/error',
            error_type='http',
            message='404 Not Found'
        )
        
        errors = state.get_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].url, 'https://example.com/error')
        self.assertEqual(errors[0].error_type, 'http')
        self.assertEqual(errors[0].message, '404 Not Found')
        self.assertIsInstance(errors[0].timestamp, float)
    
    def test_record_multiple_errors(self):
        """Should be able to record multiple errors."""
        state = self.create_crawl_state()
        
        state.record_error('https://example.com/a', 'http', '404')
        state.record_error('https://example.com/b', 'timeout', 'Connection timed out')
        state.record_error('https://example.com/c', 'ssl', 'Certificate error')
        
        errors = state.get_errors()
        self.assertEqual(len(errors), 3)
    
    def test_get_error_summary(self):
        """get_error_summary should return counts by error type."""
        state = self.create_crawl_state()
        
        state.record_error('https://example.com/a', 'http', '404')
        state.record_error('https://example.com/b', 'http', '500')
        state.record_error('https://example.com/c', 'timeout', 'Timed out')
        state.record_error('https://example.com/d', 'ssl', 'SSL error')
        state.record_error('https://example.com/e', 'http', '403')
        
        summary = state.get_error_summary()
        
        self.assertEqual(summary['http'], 3)
        self.assertEqual(summary['timeout'], 1)
        self.assertEqual(summary['ssl'], 1)
    
    def test_errors_persist_through_save_load(self):
        """Errors should be persisted and restored correctly."""
        state1 = self.create_crawl_state()
        
        state1.record_error('https://example.com/a', 'http', '404 Not Found')
        state1.record_error('https://example.com/b', 'timeout', 'Connection timed out')
        state1.save()
        
        # Load into new instance
        state2 = self.create_crawl_state()
        result = state2.load()
        
        self.assertTrue(result)
        errors = state2.get_errors()
        self.assertEqual(len(errors), 2)
        
        self.assertEqual(errors[0].url, 'https://example.com/a')
        self.assertEqual(errors[0].error_type, 'http')
        self.assertEqual(errors[0].message, '404 Not Found')
        
        self.assertEqual(errors[1].url, 'https://example.com/b')
        self.assertEqual(errors[1].error_type, 'timeout')
    
    def test_clear_removes_errors(self):
        """clear() should remove all errors."""
        state = self.create_crawl_state()
        
        state.record_error('https://example.com/a', 'http', '404')
        state.record_error('https://example.com/b', 'timeout', 'Timed out')
        
        state.clear()
        
        errors = state.get_errors()
        self.assertEqual(len(errors), 0)
    
    def test_record_error_is_thread_safe(self):
        """record_error should be thread-safe under concurrent access."""
        state = self.create_crawl_state()
        errors_list = []
        
        def record_many(start):
            try:
                for i in range(20):
                    state.record_error(
                        f'https://example.com/page{start}_{i}',
                        'http',
                        f'Error {start}_{i}'
                    )
            except Exception as e:
                errors_list.append(e)
        
        threads = [threading.Thread(target=record_many, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors_list), 0)
        # Should have 100 errors (5 threads × 20 errors each)
        self.assertEqual(len(state.get_errors()), 100)


# ============================================================================
# CrawlError Tests
# ============================================================================

class TestCrawlError(CrawlerTestCase):
    """Tests for CrawlError dataclass."""
    
    def test_crawl_error_creation(self):
        """Should create CrawlError with all fields."""
        error = CrawlError(
            url='https://example.com/page',
            error_type='http',
            message='404 Not Found',
            timestamp=1234567890.123
        )
        
        self.assertEqual(error.url, 'https://example.com/page')
        self.assertEqual(error.error_type, 'http')
        self.assertEqual(error.message, '404 Not Found')
        self.assertEqual(error.timestamp, 1234567890.123)
    
    def test_crawl_error_to_dict(self):
        """to_dict should return serializable dictionary."""
        error = CrawlError(
            url='https://example.com/page',
            error_type='timeout',
            message='Connection timed out',
            timestamp=1234567890.0
        )
        
        result = error.to_dict()
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['url'], 'https://example.com/page')
        self.assertEqual(result['error_type'], 'timeout')
        self.assertEqual(result['message'], 'Connection timed out')
        self.assertEqual(result['timestamp'], 1234567890.0)
    
    def test_crawl_error_from_dict(self):
        """from_dict should create CrawlError from dictionary."""
        data = {
            'url': 'https://example.com/page',
            'error_type': 'ssl',
            'message': 'Certificate verification failed',
            'timestamp': 1234567890.5
        }
        
        error = CrawlError.from_dict(data)
        
        self.assertEqual(error.url, 'https://example.com/page')
        self.assertEqual(error.error_type, 'ssl')
        self.assertEqual(error.message, 'Certificate verification failed')
        self.assertEqual(error.timestamp, 1234567890.5)
    
    def test_crawl_error_round_trip(self):
        """to_dict → from_dict should preserve all data."""
        original = CrawlError(
            url='https://example.com/test',
            error_type='parse',
            message='Invalid HTML structure',
            timestamp=9876543210.999
        )
        
        # Round-trip through dict
        data = original.to_dict()
        restored = CrawlError.from_dict(data)
        
        self.assertEqual(restored.url, original.url)
        self.assertEqual(restored.error_type, original.error_type)
        self.assertEqual(restored.message, original.message)
        self.assertEqual(restored.timestamp, original.timestamp)
    
    def test_crawl_error_json_serializable(self):
        """CrawlError.to_dict() should be JSON serializable."""
        error = CrawlError(
            url='https://example.com/page',
            error_type='http',
            message='500 Internal Server Error',
            timestamp=time.time()
        )
        
        # Should not raise
        json_str = json.dumps(error.to_dict())
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        self.assertEqual(parsed['url'], error.url)
    
    # -------------------------------------------------------------------------
    # Performance tests for persistent set optimization
    # -------------------------------------------------------------------------
    
    def test_add_urls_performance_with_large_queue(self):
        """add_urls should maintain O(1) lookup even with large pending queue.
        
        This tests the optimization from Phase 4.1 (#88) - using a persistent
        _pending_set instead of rebuilding the set on every add_urls call.
        """
        import time
        state = self.create_crawl_state()
        
        # Pre-populate with 10K URLs
        initial_urls = [(f'https://example.com/page{i}', 0) for i in range(10000)]
        state.add_urls(initial_urls)
        
        # Now benchmark adding more URLs
        # With O(n) set construction, this would be slow
        # With O(1) persistent set, this should be fast
        new_urls = [(f'https://example.com/new{i}', 0) for i in range(1000)]
        
        start = time.time()
        for i in range(10):  # 10 batches
            batch = [(f'https://example.com/batch{i}-{j}', 0) for j in range(100)]
            state.add_urls(batch)
        elapsed = time.time() - start
        
        # Should complete in under 100ms (with old O(n) impl would be slower)
        self.assertLess(elapsed, 0.1, f"add_urls too slow: {elapsed:.3f}s")
        
        # Verify correctness - all URLs should be in pending
        self.assertEqual(len(state.pending), 11000)  # 10K + 10*100
    
    def test_pending_set_consistency_with_pop(self):
        """_pending_set should stay consistent when popping URLs."""
        state = self.create_crawl_state()
        
        # Add some URLs
        urls = [(f'https://example.com/page{i}', 0) for i in range(5)]
        state.add_urls(urls)
        
        # Pop some URLs
        state.pop_url()
        state.pop_url()
        
        # Try to re-add the same URLs - only popped ones should be added
        state.add_urls(urls)
        
        # Should have 5 (original 3 still pending) + 2 (re-added popped ones)
        self.assertEqual(len(state.pending), 5)
    
    def test_pending_set_consistency_with_mark_failed(self):
        """_pending_set should stay consistent when mark_failed re-adds URLs."""
        state = self.create_crawl_state()
        
        # Add and pop a URL
        state.add_urls([('https://example.com/fail', 0)])
        url, depth = state.pop_url()
        
        # Mark it as failed (should re-add to pending)
        state.mark_failed(url, depth)
        
        # Try to add the same URL again - should be skipped (already in pending)
        state.add_urls([('https://example.com/fail', 0)])
        
        # Should only have 1 URL in pending
        self.assertEqual(len(state.pending), 1)


# ============================================================================
# RateLimiter Tests
# ============================================================================

class TestRateLimiter(CrawlerTestCase):
    """Tests for RateLimiter class."""
    
    # -------------------------------------------------------------------------
    # Basic delay configuration tests
    # -------------------------------------------------------------------------
    
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
    
    def test_zero_default_delay(self):
        """Should support zero delay."""
        limiter = RateLimiter(default_delay=0.0)
        self.assertEqual(limiter.get_delay('example.com'), 0.0)
    
    def test_update_domain_delay(self):
        """Should update existing domain delay."""
        limiter = RateLimiter(default_delay=0.5)
        limiter.set_domain_delay('example.com', 1.0)
        limiter.set_domain_delay('example.com', 2.0)
        
        self.assertEqual(limiter.get_delay('example.com'), 2.0)
    
    # -------------------------------------------------------------------------
    # Delay enforcement tests
    # -------------------------------------------------------------------------
    
    def test_enforces_minimum_delay_between_requests(self):
        """Should enforce minimum delay between consecutive requests."""
        delay = 0.1  # 100ms delay
        limiter = RateLimiter(default_delay=delay)
        domain = 'example.com'
        
        # First request should be immediate
        start1 = time.time()
        limiter.wait_for_domain(domain)
        elapsed1 = time.time() - start1
        
        # Second request should wait for delay
        start2 = time.time()
        limiter.wait_for_domain(domain)
        elapsed2 = time.time() - start2
        
        # First request should be nearly instant (< 50ms tolerance)
        self.assertLess(elapsed1, 0.05)
        
        # Second request should have waited approximately delay time
        # Allow 50% tolerance for timing variations
        self.assertGreaterEqual(elapsed2, delay * 0.5)
    
    def test_respects_per_domain_delay(self):
        """Should use per-domain delay instead of default."""
        limiter = RateLimiter(default_delay=1.0)  # Long default
        limiter.set_domain_delay('fast.com', 0.05)  # Short delay
        
        # First request
        limiter.wait_for_domain('fast.com')
        
        # Second request should use the short delay
        start = time.time()
        limiter.wait_for_domain('fast.com')
        elapsed = time.time() - start
        
        # Should be close to 50ms, not 1000ms (allow some tolerance)
        self.assertLess(elapsed, 0.3)  # Much less than 1.0s default
    
    def test_different_domains_dont_block_each_other(self):
        """Requests to different domains should not interfere."""
        limiter = RateLimiter(default_delay=0.5)  # 500ms delay
        
        # Make request to domain A
        limiter.wait_for_domain('domain-a.com')
        
        # Immediately make request to domain B - should not wait
        start = time.time()
        limiter.wait_for_domain('domain-b.com')
        elapsed = time.time() - start
        
        # Should be nearly instant (domains are independent)
        self.assertLess(elapsed, 0.1)
    
    def test_multiple_domains_tracked_independently(self):
        """Each domain should have its own timing."""
        limiter = RateLimiter(default_delay=0.1)
        
        # Request to one domain, then immediately to another
        # Second domain should not be affected by first
        limiter.wait_for_domain('domain1.com')
        
        # Immediately request domain2 - should be instant (different domain)
        start = time.time()
        limiter.wait_for_domain('domain2.com')
        elapsed = time.time() - start
        self.assertLess(elapsed, 0.05)  # Should be instant
        
        # Now request domain1 again immediately - should wait
        start = time.time()
        limiter.wait_for_domain('domain1.com')
        elapsed = time.time() - start
        self.assertGreaterEqual(elapsed, 0.05)  # Should wait for delay
    
    # -------------------------------------------------------------------------
    # Backoff tests
    # -------------------------------------------------------------------------
    
    def test_backoff_delays_requests(self):
        """set_backoff should delay subsequent requests."""
        limiter = RateLimiter(default_delay=0.0)  # No normal delay
        domain = 'example.com'
        
        # Set short backoff (100ms)
        limiter.set_backoff(domain, 0.1)
        
        # Request should be delayed
        start = time.time()
        limiter.wait_for_domain(domain)
        elapsed = time.time() - start
        
        # Should have waited for backoff
        self.assertGreaterEqual(elapsed, 0.05)  # At least half the backoff
    
    def test_backoff_expires(self):
        """Backoff should expire after the specified time."""
        limiter = RateLimiter(default_delay=0.0)
        domain = 'example.com'
        
        # Set very short backoff
        limiter.set_backoff(domain, 0.05)
        
        # Wait for backoff to expire
        time.sleep(0.1)
        
        # Request should be immediate (backoff expired)
        start = time.time()
        limiter.wait_for_domain(domain)
        elapsed = time.time() - start
        
        self.assertLess(elapsed, 0.05)  # Should be nearly instant
    
    def test_backoff_overrides_normal_delay(self):
        """Backoff should take precedence over normal delay."""
        limiter = RateLimiter(default_delay=0.05)
        domain = 'example.com'
        
        # Make initial request to start timing
        limiter.wait_for_domain(domain)
        
        # Set longer backoff
        limiter.set_backoff(domain, 0.15)
        
        # Should wait for backoff (longer than normal delay)
        start = time.time()
        limiter.wait_for_domain(domain)
        elapsed = time.time() - start
        
        # Should be closer to backoff time than normal delay
        self.assertGreaterEqual(elapsed, 0.1)
    
    def test_backoff_only_affects_specified_domain(self):
        """Backoff on one domain should not affect others."""
        limiter = RateLimiter(default_delay=0.0)
        
        # Set backoff on domain A
        limiter.set_backoff('domain-a.com', 1.0)  # Long backoff
        
        # Domain B should be unaffected
        start = time.time()
        limiter.wait_for_domain('domain-b.com')
        elapsed = time.time() - start
        
        self.assertLess(elapsed, 0.05)  # Should be instant
    
    # -------------------------------------------------------------------------
    # Thread safety tests
    # -------------------------------------------------------------------------
    
    def test_concurrent_wait_for_domain_is_thread_safe(self):
        """wait_for_domain should be thread-safe under concurrent access."""
        limiter = RateLimiter(default_delay=0.01)  # 10ms delay
        domain = 'example.com'
        errors = []
        request_times = []
        lock = threading.Lock()
        
        def make_requests():
            try:
                for _ in range(5):
                    limiter.wait_for_domain(domain)
                    with lock:
                        request_times.append(time.time())
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=make_requests) for _ in range(3)]
        start_time = time.time()
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)
        # Should have 15 requests total (3 threads × 5 requests)
        self.assertEqual(len(request_times), 15)
    
    def test_concurrent_set_domain_delay_is_thread_safe(self):
        """set_domain_delay should be thread-safe."""
        limiter = RateLimiter(default_delay=0.5)
        errors = []
        
        def set_delays(start):
            try:
                for i in range(20):
                    limiter.set_domain_delay(f'domain{start}_{i}.com', 0.1 * i)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=set_delays, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        self.assertEqual(len(errors), 0)


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
# Incremental Crawl Tests
# ============================================================================

class TestIncrementalCrawl(CrawlerTestCase):
    """Tests for incremental crawling functionality."""
    
    def test_content_hash_deterministic(self):
        """_content_hash should produce consistent hashes."""
        crawler = self.create_crawler()
        
        content = "Hello, World!"
        hash1 = crawler._content_hash(content)
        hash2 = crawler._content_hash(content)
        
        self.assertEqual(hash1, hash2)
    
    def test_content_hash_different_for_different_content(self):
        """_content_hash should produce different hashes for different content."""
        crawler = self.create_crawler()
        
        hash1 = crawler._content_hash("Content A")
        hash2 = crawler._content_hash("Content B")
        
        self.assertNotEqual(hash1, hash2)
    
    def test_content_hash_is_sha256(self):
        """_content_hash should return 64-character SHA256 hash."""
        crawler = self.create_crawler()
        
        hash_value = crawler._content_hash("Test content")
        
        self.assertEqual(len(hash_value), 64)
        # Should be valid hex
        int(hash_value, 16)
    
    def test_get_page_metadata_returns_none_for_missing_file(self):
        """_get_page_metadata should return None when page file doesn't exist."""
        crawler = self.create_crawler()
        
        result = crawler._get_page_metadata('https://example.com/nonexistent')
        
        self.assertIsNone(result)
    
    def test_get_page_metadata_loads_existing_page(self):
        """_get_page_metadata should load data from existing page file."""
        crawler = self.create_crawler()
        
        # Create a page file
        from doc_search.utils import url_to_filename
        url = 'https://example.com/test'
        filename = url_to_filename(url) + '.json'
        page_data = {
            'url': url,
            'title': 'Test Page',
            'etag': '"abc123"',
            'last_modified': 'Wed, 01 Jan 2020 00:00:00 GMT',
            'content_hash': 'somehash123',
        }
        
        with open(crawler.pages_dir / filename, 'w') as f:
            json.dump(page_data, f)
        
        result = crawler._get_page_metadata(url)
        
        self.assertEqual(result['title'], 'Test Page')
        self.assertEqual(result['etag'], '"abc123"')
        self.assertEqual(result['last_modified'], 'Wed, 01 Jan 2020 00:00:00 GMT')
    
    def test_get_page_metadata_handles_corrupted_json(self):
        """_get_page_metadata should return None for corrupted JSON."""
        crawler = self.create_crawler()
        
        from doc_search.utils import url_to_filename
        url = 'https://example.com/corrupted'
        filename = url_to_filename(url) + '.json'
        
        with open(crawler.pages_dir / filename, 'w') as f:
            f.write('{ invalid json }}}')
        
        result = crawler._get_page_metadata(url)
        
        self.assertIsNone(result)
    
    def test_save_page_stores_incremental_metadata(self):
        """_save_page should store etag, last_modified, and content_hash."""
        crawler = self.create_crawler()
        
        url = 'https://example.com/testpage'
        page_data = {
            'url': url,
            'title': 'Test Page',
            'description': 'A test page',
            'text': 'Page content here',
            'headings': [],
            'depth': 0,
            'crawled_at': time.time(),
            'etag': '"abc123"',
            'last_modified': 'Wed, 01 Jan 2020 00:00:00 GMT',
            'content_hash': 'hash123',
        }
        
        crawler._save_page(url, page_data)
        
        # Verify the file was saved
        from doc_search.utils import url_to_filename
        filename = url_to_filename(url) + '.json'
        filepath = crawler.pages_dir / filename
        
        self.assertTrue(filepath.exists())
        
        with open(filepath) as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data['etag'], '"abc123"')
        self.assertEqual(saved_data['last_modified'], 'Wed, 01 Jan 2020 00:00:00 GMT')
        self.assertEqual(saved_data['content_hash'], 'hash123')
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_sends_etag_header(self, mock_urlopen):
        """_fetch should send If-None-Match header when etag is provided."""
        crawler = self.create_crawler()
        
        mock_response = create_mock_response('<html></html>')
        mock_urlopen.return_value = mock_response
        
        crawler._fetch('https://example.com/', etag='"abc123"')
        
        # Check the request was made with If-None-Match header
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        self.assertEqual(request.get_header('If-none-match'), '"abc123"')
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_sends_last_modified_header(self, mock_urlopen):
        """_fetch should send If-Modified-Since header when last_modified is provided."""
        crawler = self.create_crawler()
        
        mock_response = create_mock_response('<html></html>')
        mock_urlopen.return_value = mock_response
        
        last_mod = 'Wed, 01 Jan 2020 00:00:00 GMT'
        crawler._fetch('https://example.com/', last_modified=last_mod)
        
        # Check the request was made with If-Modified-Since header
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        self.assertEqual(request.get_header('If-modified-since'), last_mod)
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_handles_304_not_modified(self, mock_urlopen):
        """_fetch should return not_modified=True on HTTP 304."""
        crawler = self.create_crawler()
        
        # Simulate 304 response
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/', 304, 'Not Modified', {}, None
        )
        
        content, content_type, metadata = crawler._fetch(
            'https://example.com/', 
            etag='"abc123"'
        )
        
        self.assertIsNone(content)
        self.assertIsNone(content_type)
        self.assertTrue(metadata.get('not_modified'))
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_etag_from_response(self, mock_urlopen):
        """_fetch should capture ETag from response headers."""
        crawler = self.create_crawler()
        
        mock_response = create_mock_response(
            '<html></html>',
            etag='"newetag456"'
        )
        mock_urlopen.return_value = mock_response
        
        content, content_type, metadata = crawler._fetch('https://example.com/')
        
        self.assertEqual(metadata.get('etag'), '"newetag456"')
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_last_modified_from_response(self, mock_urlopen):
        """_fetch should capture Last-Modified from response headers."""
        crawler = self.create_crawler()
        
        mock_response = create_mock_response(
            '<html></html>',
            last_modified='Wed, 15 Jan 2025 12:00:00 GMT'
        )
        mock_urlopen.return_value = mock_response
        
        content, content_type, metadata = crawler._fetch('https://example.com/')
        
        self.assertEqual(metadata.get('last_modified'), 'Wed, 15 Jan 2025 12:00:00 GMT')
    
    def test_unchanged_page_detection_via_content_hash(self):
        """Should detect unchanged pages via content hash comparison."""
        crawler = self.create_crawler(incremental=True)
        
        # Simulate previously crawled page
        from doc_search.utils import url_to_filename
        url = 'https://example.com/page'
        content = '<html><head><title>Test</title></head><body>Content</body></html>'
        content_hash = crawler._content_hash(content)
        
        page_data = {
            'url': url,
            'title': 'Test',
            'description': '',
            'text': 'Content',
            'headings': [],
            'depth': 0,
            'crawled_at': time.time(),
            'content_hash': content_hash,
        }
        
        filename = url_to_filename(url) + '.json'
        with open(crawler.pages_dir / filename, 'w') as f:
            json.dump(page_data, f)
        
        # Load and verify
        loaded = crawler._get_page_metadata(url)
        self.assertEqual(loaded['content_hash'], content_hash)
        
        # New content with same hash would be detected as unchanged
        new_content_hash = crawler._content_hash(content)
        self.assertEqual(new_content_hash, loaded['content_hash'])
    
    def test_changed_page_detection_via_content_hash(self):
        """Should detect changed pages via content hash comparison."""
        crawler = self.create_crawler(incremental=True)
        
        original_content = '<html><body>Original</body></html>'
        modified_content = '<html><body>Modified</body></html>'
        
        original_hash = crawler._content_hash(original_content)
        modified_hash = crawler._content_hash(modified_content)
        
        # Hashes should be different
        self.assertNotEqual(original_hash, modified_hash)
    
    def test_incremental_mode_flag(self):
        """Crawler should have incremental mode flag."""
        crawler_default = self.create_crawler()
        crawler_incremental = self.create_crawler(incremental=True)
        
        self.assertFalse(crawler_default.incremental)
        self.assertTrue(crawler_incremental.incremental)


# ============================================================================
# Crawl Error Recording Tests
# ============================================================================

class TestCrawlErrorRecording(CrawlerTestCase):
    """Tests for error recording during crawling."""
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_http_error_metadata_for_404(self, mock_urlopen):
        """_fetch should return error metadata for HTTP 404."""
        crawler = self.create_crawler()
        
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/notfound', 404, 'Not Found', {}, None
        )
        
        content, content_type, metadata = crawler._fetch('https://example.com/notfound')
        
        self.assertIsNone(content)
        self.assertEqual(metadata.get('error_type'), 'http')
        self.assertIn('404', metadata.get('error_message', ''))
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_http_error_metadata_for_500(self, mock_urlopen):
        """_fetch should return error metadata for HTTP 500."""
        crawler = self.create_crawler()
        
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/error', 500, 'Internal Server Error', {}, None
        )
        
        content, content_type, metadata = crawler._fetch('https://example.com/error')
        
        self.assertIsNone(content)
        self.assertEqual(metadata.get('error_type'), 'http')
        self.assertIn('500', metadata.get('error_message', ''))
        self.assertIn('Server error', metadata.get('error_message', ''))
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_http_error_metadata_for_429(self, mock_urlopen):
        """_fetch should return error metadata for HTTP 429 (rate limited)."""
        crawler = self.create_crawler()
        
        error = HTTPError(
            'https://example.com/ratelimited', 429, 'Too Many Requests', {}, None
        )
        error.headers = MagicMock()
        error.headers.get = lambda key, default: '60' if key == 'Retry-After' else default
        mock_urlopen.side_effect = error
        
        content, content_type, metadata = crawler._fetch('https://example.com/ratelimited')
        
        self.assertIsNone(content)
        self.assertEqual(metadata.get('error_type'), 'http')
        self.assertIn('429', metadata.get('error_message', ''))
        self.assertIn('Rate limited', metadata.get('error_message', ''))
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_timeout_error_metadata(self, mock_urlopen):
        """_fetch should return timeout error metadata."""
        crawler = self.create_crawler()
        
        mock_urlopen.side_effect = URLError('timed out')
        
        content, content_type, metadata = crawler._fetch('https://example.com/slow')
        
        self.assertIsNone(content)
        self.assertEqual(metadata.get('error_type'), 'timeout')
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_ssl_error_metadata(self, mock_urlopen):
        """_fetch should return SSL error metadata."""
        crawler = self.create_crawler()
        
        mock_urlopen.side_effect = URLError('SSL: CERTIFICATE_VERIFY_FAILED')
        
        content, content_type, metadata = crawler._fetch('https://example.com/badcert')
        
        self.assertIsNone(content)
        self.assertEqual(metadata.get('error_type'), 'ssl')
    
    @patch('doc_search.crawler.urlopen')
    def test_fetch_returns_network_error_metadata(self, mock_urlopen):
        """_fetch should return network error metadata for connection errors."""
        crawler = self.create_crawler()
        
        mock_urlopen.side_effect = URLError('Connection refused')
        
        content, content_type, metadata = crawler._fetch('https://example.com/down')
        
        self.assertIsNone(content)
        self.assertEqual(metadata.get('error_type'), 'network')
        self.assertIn('Connection refused', metadata.get('error_message', ''))
    
    @patch('doc_search.crawler.urlopen')
    def test_process_page_records_http_error(self, mock_urlopen):
        """_process_page should record HTTP errors in crawl state."""
        crawler = self.create_crawler()
        crawler.robots.can_fetch = Mock(return_value=True)
        
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/notfound', 404, 'Not Found', {}, None
        )
        
        # Process page should record the error
        result = crawler._process_page('https://example.com/notfound', depth=0)
        
        self.assertIsNone(result)
        
        # Check error was recorded
        errors = crawler.state.get_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].url, 'https://example.com/notfound')
        self.assertEqual(errors[0].error_type, 'http')
        self.assertIn('404', errors[0].message)
    
    @patch('doc_search.crawler.urlopen')
    def test_process_page_records_timeout_error(self, mock_urlopen):
        """_process_page should record timeout errors in crawl state."""
        crawler = self.create_crawler()
        crawler.robots.can_fetch = Mock(return_value=True)
        
        mock_urlopen.side_effect = URLError('Connection timed out')
        
        result = crawler._process_page('https://example.com/slow', depth=0)
        
        self.assertIsNone(result)
        
        errors = crawler.state.get_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].error_type, 'timeout')
    
    @patch('doc_search.crawler.urlopen')
    def test_process_page_records_ssl_error(self, mock_urlopen):
        """_process_page should record SSL errors in crawl state."""
        crawler = self.create_crawler()
        crawler.robots.can_fetch = Mock(return_value=True)
        
        mock_urlopen.side_effect = URLError('SSL certificate verification failed')
        
        result = crawler._process_page('https://example.com/badcert', depth=0)
        
        self.assertIsNone(result)
        
        errors = crawler.state.get_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].error_type, 'ssl')
    
    @patch('doc_search.crawler.urlopen')
    def test_multiple_errors_recorded(self, mock_urlopen):
        """Should record multiple errors for multiple failed pages."""
        crawler = self.create_crawler()
        crawler.robots.can_fetch = Mock(return_value=True)
        
        # First page - 404
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/page1', 404, 'Not Found', {}, None
        )
        crawler._process_page('https://example.com/page1', depth=0)
        
        # Second page - 500
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/page2', 500, 'Server Error', {}, None
        )
        crawler._process_page('https://example.com/page2', depth=0)
        
        # Third page - timeout
        mock_urlopen.side_effect = URLError('Connection timed out')
        crawler._process_page('https://example.com/page3', depth=0)
        
        errors = crawler.state.get_errors()
        self.assertEqual(len(errors), 3)
        
        # Check error summary
        summary = crawler.state.get_error_summary()
        self.assertEqual(summary['http'], 2)
        self.assertEqual(summary['timeout'], 1)
    
    @patch('doc_search.crawler.urlopen')
    def test_errors_persist_through_checkpoint(self, mock_urlopen):
        """Errors should be saved and restored through checkpoints."""
        crawler = self.create_crawler()
        crawler.robots.can_fetch = Mock(return_value=True)
        
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/error', 404, 'Not Found', {}, None
        )
        
        crawler._process_page('https://example.com/error', depth=0)
        
        # Save state
        crawler.state.save()
        
        # Create new crawler instance and load state
        crawler2 = self.create_crawler()
        crawler2.state.load()
        
        # Errors should be restored
        errors = crawler2.state.get_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].url, 'https://example.com/error')
        self.assertEqual(errors[0].error_type, 'http')


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
