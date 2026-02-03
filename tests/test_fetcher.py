"""
Tests for the HTTP fetcher module.
"""

import gzip
import ssl
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

from doc_search.crawler.fetcher import Fetcher, FetchResult
from doc_search.rate_limiter import RateLimiter


# ============================================================================
# Test Fixtures
# ============================================================================

def create_mock_response(
    content: str,
    status: int = 200,
    content_type: str = 'text/html; charset=utf-8',
    content_encoding: str = '',
    etag: Optional[str] = None,
    last_modified: Optional[str] = None
):
    """Create a mock HTTP response object."""
    mock_response = MagicMock()
    mock_response.read.return_value = content.encode('utf-8')
    mock_response.status = status
    mock_response.code = status
    
    # Create headers dict-like object
    headers = {
        'Content-Type': content_type,
        'Content-Encoding': content_encoding,
    }
    if etag:
        headers['ETag'] = etag
    if last_modified:
        headers['Last-Modified'] = last_modified
    
    mock_response.headers = MagicMock()
    mock_response.headers.get = lambda key, default='': headers.get(key, default)
    
    return mock_response


def create_gzip_mock_response(content: str, **kwargs):
    """Create a mock HTTP response with gzip-compressed content."""
    compressed = gzip.compress(content.encode('utf-8'))
    mock_response = MagicMock()
    mock_response.read.return_value = compressed
    mock_response.status = 200
    mock_response.code = 200
    
    headers = {
        'Content-Type': kwargs.get('content_type', 'text/html; charset=utf-8'),
        'Content-Encoding': 'gzip',
        'ETag': kwargs.get('etag'),
        'Last-Modified': kwargs.get('last_modified'),
    }
    
    mock_response.headers = MagicMock()
    mock_response.headers.get = lambda key, default='': headers.get(key, default)
    
    return mock_response


# ============================================================================
# FetchResult Tests
# ============================================================================

class TestFetchResult(unittest.TestCase):
    """Tests for FetchResult dataclass."""
    
    def test_success_with_content(self):
        """FetchResult with content should be successful."""
        result = FetchResult(
            content='<html>Hello</html>',
            content_type='text/html',
            metadata={'etag': '"abc123"'}
        )
        
        self.assertTrue(result.success)
        self.assertFalse(result.not_modified)
        self.assertEqual(result.content, '<html>Hello</html>')
        self.assertEqual(result.content_type, 'text/html')
        self.assertEqual(result.metadata['etag'], '"abc123"')
    
    def test_not_modified_result(self):
        """FetchResult with not_modified should indicate unchanged content."""
        result = FetchResult(metadata={'not_modified': True})
        
        self.assertFalse(result.success)
        self.assertTrue(result.not_modified)
        self.assertIsNone(result.content)
    
    def test_error_result(self):
        """FetchResult with error should indicate failure."""
        result = FetchResult(metadata={
            'error_type': 'http',
            'error_message': 'HTTP 404'
        })
        
        self.assertFalse(result.success)
        self.assertFalse(result.not_modified)
        self.assertEqual(result.error_type, 'http')
        self.assertEqual(result.error_message, 'HTTP 404')
    
    def test_as_tuple(self):
        """as_tuple should return backward-compatible format."""
        result = FetchResult(
            content='Hello',
            content_type='text/plain',
            metadata={'etag': '"xyz"'}
        )
        
        content, content_type, metadata = result.as_tuple()
        
        self.assertEqual(content, 'Hello')
        self.assertEqual(content_type, 'text/plain')
        self.assertEqual(metadata['etag'], '"xyz"')
    
    def test_empty_result(self):
        """Default FetchResult should indicate failure."""
        result = FetchResult()
        
        self.assertFalse(result.success)
        self.assertFalse(result.not_modified)
        self.assertIsNone(result.content)
        self.assertIsNone(result.content_type)
        self.assertEqual(result.metadata, {})


# ============================================================================
# Fetcher Tests
# ============================================================================

class TestFetcher(unittest.TestCase):
    """Tests for Fetcher class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a fetcher with no delays for testing
        self.rate_limiter = RateLimiter(default_delay=0.0)
        self.fetcher = Fetcher(
            delay=0.0,
            timeout=5.0,
            rate_limiter=self.rate_limiter
        )
    
    # -------------------------------------------------------------------------
    # Successful fetch tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_success(self, mock_urlopen):
        """Should fetch and return content successfully."""
        mock_urlopen.return_value = create_mock_response(
            '<html><body>Hello World</body></html>',
            content_type='text/html; charset=utf-8'
        )
        
        result = self.fetcher.fetch('https://example.com/page')
        
        self.assertTrue(result.success)
        self.assertIn('Hello World', result.content)
        self.assertEqual(result.content_type, 'text/html; charset=utf-8')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_returns_etag_and_last_modified(self, mock_urlopen):
        """Should capture ETag and Last-Modified headers."""
        mock_urlopen.return_value = create_mock_response(
            '<html></html>',
            etag='"abc123"',
            last_modified='Wed, 21 Oct 2015 07:28:00 GMT'
        )
        
        result = self.fetcher.fetch('https://example.com/page')
        
        self.assertEqual(result.metadata['etag'], '"abc123"')
        self.assertEqual(result.metadata['last_modified'], 'Wed, 21 Oct 2015 07:28:00 GMT')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_gzip_content(self, mock_urlopen):
        """Should decompress gzip-encoded content."""
        mock_urlopen.return_value = create_gzip_mock_response(
            '<html><body>Compressed Content</body></html>'
        )
        
        result = self.fetcher.fetch('https://example.com/page')
        
        self.assertTrue(result.success)
        self.assertIn('Compressed Content', result.content)
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_utf8_content(self, mock_urlopen):
        """Should decode UTF-8 content correctly."""
        mock_urlopen.return_value = create_mock_response(
            '<html><body>Héllo Wörld 你好</body></html>',
            content_type='text/html; charset=utf-8'
        )
        
        result = self.fetcher.fetch('https://example.com/page')
        
        self.assertTrue(result.success)
        self.assertIn('Héllo', result.content)
        self.assertIn('你好', result.content)
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_charset_in_content_type(self, mock_urlopen):
        """Should extract charset from Content-Type header."""
        # Create response with ISO-8859-1 content
        content_bytes = 'Héllo'.encode('iso-8859-1')
        mock_response = MagicMock()
        mock_response.read.return_value = content_bytes
        mock_response.headers = MagicMock()
        mock_response.headers.get = lambda key, default='': {
            'Content-Type': 'text/html; charset=iso-8859-1',
            'Content-Encoding': '',
        }.get(key, default)
        mock_urlopen.return_value = mock_response
        
        result = self.fetcher.fetch('https://example.com/page')
        
        self.assertTrue(result.success)
        self.assertIn('Héllo', result.content)
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_missing_charset(self, mock_urlopen):
        """Should default to UTF-8 when charset is missing."""
        mock_urlopen.return_value = create_mock_response(
            '<html></html>',
            content_type='text/html'  # No charset
        )
        
        result = self.fetcher.fetch('https://example.com/page')
        
        self.assertTrue(result.success)
    
    # -------------------------------------------------------------------------
    # Conditional request tests (ETag/Last-Modified)
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_sends_etag_header(self, mock_urlopen):
        """Should send If-None-Match header when etag provided."""
        mock_urlopen.return_value = create_mock_response('<html></html>')
        
        self.fetcher.fetch('https://example.com/page', etag='"abc123"')
        
        # Check that the request was made with the header
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        self.assertEqual(request.get_header('If-none-match'), '"abc123"')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_sends_last_modified_header(self, mock_urlopen):
        """Should send If-Modified-Since header when last_modified provided."""
        mock_urlopen.return_value = create_mock_response('<html></html>')
        
        self.fetcher.fetch(
            'https://example.com/page',
            last_modified='Wed, 21 Oct 2015 07:28:00 GMT'
        )
        
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        self.assertEqual(
            request.get_header('If-modified-since'),
            'Wed, 21 Oct 2015 07:28:00 GMT'
        )
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_304_not_modified(self, mock_urlopen):
        """Should handle 304 Not Modified response."""
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/page', 304, 'Not Modified', {}, None
        )
        
        result = self.fetcher.fetch('https://example.com/page', etag='"abc123"')
        
        self.assertFalse(result.success)
        self.assertTrue(result.not_modified)
        self.assertIsNone(result.content)
    
    # -------------------------------------------------------------------------
    # HTTP error handling tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_404_error(self, mock_urlopen):
        """Should handle 404 Not Found error."""
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/missing', 404, 'Not Found', {}, None
        )
        
        result = self.fetcher.fetch('https://example.com/missing')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'http')
        self.assertIn('404', result.error_message)
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_500_server_error(self, mock_urlopen):
        """Should handle 500 Internal Server Error."""
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/error', 500, 'Internal Server Error', {}, None
        )
        
        result = self.fetcher.fetch('https://example.com/error')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'http')
        self.assertIn('500', result.error_message)
        self.assertIn('Server error', result.error_message)
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_429_rate_limit(self, mock_urlopen):
        """Should handle 429 Too Many Requests and set backoff."""
        mock_headers = MagicMock()
        mock_headers.get = lambda key, default=None: '60' if key == 'Retry-After' else default
        
        error = HTTPError(
            'https://example.com/limited', 429, 'Too Many Requests',
            mock_headers, None
        )
        mock_urlopen.side_effect = error
        
        result = self.fetcher.fetch('https://example.com/limited')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'http')
        self.assertIn('429', result.error_message)
        self.assertIn('Rate limited', result.error_message)
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_403_forbidden(self, mock_urlopen):
        """Should handle 403 Forbidden error."""
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/forbidden', 403, 'Forbidden', {}, None
        )
        
        result = self.fetcher.fetch('https://example.com/forbidden')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'http')
        self.assertIn('403', result.error_message)
    
    # -------------------------------------------------------------------------
    # Network error handling tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_connection_timeout(self, mock_urlopen):
        """Should handle connection timeout."""
        mock_urlopen.side_effect = URLError('timed out')
        
        result = self.fetcher.fetch('https://example.com/slow')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'timeout')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_timeout_error(self, mock_urlopen):
        """Should handle TimeoutError exception."""
        mock_urlopen.side_effect = TimeoutError('Connection timed out')
        
        result = self.fetcher.fetch('https://example.com/timeout')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'timeout')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_ssl_error(self, mock_urlopen):
        """Should handle SSL certificate errors."""
        mock_urlopen.side_effect = URLError('SSL: certificate verify failed')
        
        result = self.fetcher.fetch('https://example.com/badcert')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'ssl')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_ssl_exception(self, mock_urlopen):
        """Should handle ssl.SSLError exception."""
        mock_urlopen.side_effect = ssl.SSLError('certificate verify failed')
        
        result = self.fetcher.fetch('https://example.com/badcert')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'ssl')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_network_error(self, mock_urlopen):
        """Should handle network errors."""
        mock_urlopen.side_effect = URLError('Name or service not known')
        
        result = self.fetcher.fetch('https://nonexistent.invalid/')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'network')
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_handles_unknown_error(self, mock_urlopen):
        """Should handle unexpected errors gracefully."""
        mock_urlopen.side_effect = Exception('Something unexpected')
        
        result = self.fetcher.fetch('https://example.com/weird')
        
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, 'unknown')
        self.assertIn('unexpected', result.error_message)
    
    # -------------------------------------------------------------------------
    # Authentication tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_sends_basic_auth_header(self, mock_urlopen):
        """Should send Basic Auth header when credentials provided."""
        mock_urlopen.return_value = create_mock_response('<html></html>')
        
        fetcher = Fetcher(
            auth=('user', 'pass'),
            rate_limiter=self.rate_limiter
        )
        
        fetcher.fetch('https://example.com/protected')
        
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        auth_header = request.get_header('Authorization')
        self.assertIsNotNone(auth_header)
        self.assertTrue(auth_header.startswith('Basic '))
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_sends_auth_token(self, mock_urlopen):
        """Should send pre-encoded auth token when provided."""
        mock_urlopen.return_value = create_mock_response('<html></html>')
        
        fetcher = Fetcher(
            auth_token='dXNlcjpwYXNz',  # base64 of 'user:pass'
            rate_limiter=self.rate_limiter
        )
        
        fetcher.fetch('https://example.com/protected')
        
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        auth_header = request.get_header('Authorization')
        self.assertEqual(auth_header, 'Basic dXNlcjpwYXNz')
    
    # -------------------------------------------------------------------------
    # User-Agent tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_sends_default_user_agent(self, mock_urlopen):
        """Should send default User-Agent header."""
        mock_urlopen.return_value = create_mock_response('<html></html>')
        
        self.fetcher.fetch('https://example.com/page')
        
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        user_agent = request.get_header('User-agent')
        self.assertIn('DocSearchBot', user_agent)
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_sends_custom_user_agent(self, mock_urlopen):
        """Should send custom User-Agent when configured."""
        mock_urlopen.return_value = create_mock_response('<html></html>')
        
        fetcher = Fetcher(
            user_agent='CustomBot/1.0',
            rate_limiter=self.rate_limiter
        )
        
        fetcher.fetch('https://example.com/page')
        
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        user_agent = request.get_header('User-agent')
        self.assertEqual(user_agent, 'CustomBot/1.0')
    
    # -------------------------------------------------------------------------
    # Rate limiting tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_uses_rate_limiter(self, mock_urlopen):
        """Should use rate limiter between requests."""
        mock_urlopen.return_value = create_mock_response('<html></html>')
        
        # Create fetcher with small delay
        rate_limiter = RateLimiter(default_delay=0.05)
        fetcher = Fetcher(rate_limiter=rate_limiter)
        
        # First request (immediate)
        start = time.time()
        fetcher.fetch('https://example.com/page1')
        first_elapsed = time.time() - start
        
        # Second request (should wait)
        start = time.time()
        fetcher.fetch('https://example.com/page2')
        second_elapsed = time.time() - start
        
        # First should be fast
        self.assertLess(first_elapsed, 0.05)
        # Second should wait for rate limit
        self.assertGreaterEqual(second_elapsed, 0.02)
    
    # -------------------------------------------------------------------------
    # Stats callback tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_calls_stats_callback(self, mock_urlopen):
        """Should call stats callback with bytes downloaded."""
        mock_urlopen.return_value = create_mock_response('<html>Content</html>')
        
        stats = {}
        def stats_callback(name, value):
            stats[name] = stats.get(name, 0) + value
        
        fetcher = Fetcher(
            rate_limiter=self.rate_limiter,
            stats_callback=stats_callback
        )
        
        fetcher.fetch('https://example.com/page')
        
        self.assertIn('bytes_downloaded', stats)
        self.assertGreater(stats['bytes_downloaded'], 0)
    
    # -------------------------------------------------------------------------
    # Logging tests
    # -------------------------------------------------------------------------
    
    @patch('doc_search.crawler.fetcher.urlopen')
    def test_fetch_calls_log_func_on_error(self, mock_urlopen):
        """Should call log function on errors."""
        mock_urlopen.side_effect = HTTPError(
            'https://example.com/error', 404, 'Not Found', {}, None
        )
        
        logs = []
        def log_func(msg):
            logs.append(msg)
        
        fetcher = Fetcher(
            rate_limiter=self.rate_limiter,
            log_func=log_func
        )
        
        fetcher.fetch('https://example.com/error')
        
        self.assertGreater(len(logs), 0)
        self.assertTrue(any('404' in log for log in logs))


# ============================================================================
# Integration Tests
# ============================================================================

class TestFetcherIntegration(unittest.TestCase):
    """Integration tests for Fetcher with real components."""
    
    def test_fetcher_with_default_rate_limiter(self):
        """Fetcher should create its own rate limiter if not provided."""
        fetcher = Fetcher(delay=0.1)
        
        self.assertIsNotNone(fetcher.rate_limiter)
        self.assertEqual(fetcher.rate_limiter.get_delay('example.com'), 0.1)
    
    def test_fetcher_with_default_ssl_context(self):
        """Fetcher should create a permissive SSL context if not provided."""
        fetcher = Fetcher()
        
        self.assertIsNotNone(fetcher.ssl_context)
    
    def test_fetcher_build_headers(self):
        """Should build correct request headers."""
        fetcher = Fetcher(user_agent='TestBot/1.0')
        
        headers = fetcher._build_headers()
        
        self.assertEqual(headers['User-Agent'], 'TestBot/1.0')
        self.assertIn('text/html', headers['Accept'])
        self.assertIn('gzip', headers['Accept-Encoding'])
    
    def test_fetcher_build_headers_with_conditional(self):
        """Should include conditional headers when provided."""
        fetcher = Fetcher()
        
        headers = fetcher._build_headers(
            etag='"abc"',
            last_modified='Wed, 21 Oct 2015 07:28:00 GMT'
        )
        
        self.assertEqual(headers['If-None-Match'], '"abc"')
        self.assertEqual(headers['If-Modified-Since'], 'Wed, 21 Oct 2015 07:28:00 GMT')


if __name__ == '__main__':
    unittest.main()
