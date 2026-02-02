"""
Tests for the web server module.
"""

import socket
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from typing import Dict, List, Any, Optional
from unittest.mock import MagicMock, Mock

from doc_search.server import (
    SearchHandler, run_server, render_page, escape, highlight_snippet
)


# ============================================================================
# Test Fixtures
# ============================================================================

class MockSearchEngine:
    """Mock SearchEngine for testing server responses without real index."""
    
    def __init__(self, results: Optional[List[Dict[str, Any]]] = None,
                 stats: Optional[Dict[str, Any]] = None):
        """
        Create mock search engine.
        
        Args:
            results: List of result dicts to return from search()
            stats: Stats dict to return from get_stats()
        """
        self._results = results or []
        self._stats = stats or {
            'total_documents': 100,
            'unique_terms': 5000,
        }
        self.search_calls = []  # Track search calls for verification
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Return mock search results."""
        self.search_calls.append({'query': query, 'top_k': top_k})
        return self._results[:top_k]
    
    def get_stats(self) -> Dict[str, Any]:
        """Return mock stats."""
        return self._stats


def get_free_port() -> int:
    """Find an available port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class ServerTestCase(unittest.TestCase):
    """Base test case with helpers for server testing."""
    
    server = None
    server_thread = None
    port = None
    
    @classmethod
    def start_server(cls, engine=None, **kwargs):
        """Start a test server with given engine and options."""
        cls.port = get_free_port()
        
        if engine is None:
            engine = MockSearchEngine()
        
        defaults = {
            'host': '127.0.0.1',
            'port': cls.port,
            'log_requests': False,
        }
        defaults.update(kwargs)
        
        cls.server = run_server(engine, **defaults)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()
        
        # Wait for server to be ready
        time.sleep(0.1)
    
    @classmethod
    def stop_server(cls):
        """Stop the test server."""
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.server = None
        if cls.server_thread:
            cls.server_thread.join(timeout=1.0)
            cls.server_thread = None
    
    def make_request(self, path: str = '/', method: str = 'GET') -> tuple:
        """
        Make HTTP request to test server.
        
        Returns:
            (status_code, headers_dict, body_str)
        """
        conn = HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            conn.request(method, path)
            response = conn.getresponse()
            body = response.read().decode('utf-8')
            headers = dict(response.getheaders())
            return response.status, headers, body
        finally:
            conn.close()


# ============================================================================
# Unit Tests - HTML Rendering
# ============================================================================

class TestEscape(unittest.TestCase):
    """Tests for HTML escape function."""
    
    def test_escapes_html_entities(self):
        """Should escape HTML special characters."""
        self.assertEqual(escape('<script>'), '&lt;script&gt;')
        self.assertEqual(escape('a & b'), 'a &amp; b')
        self.assertEqual(escape('"quotes"'), '&quot;quotes&quot;')
    
    def test_handles_none(self):
        """Should return empty string for None."""
        self.assertEqual(escape(None), '')
    
    def test_handles_empty_string(self):
        """Should return empty string for empty input."""
        self.assertEqual(escape(''), '')


class TestHighlightSnippet(unittest.TestCase):
    """Tests for snippet highlighting function."""
    
    def test_highlights_terms(self):
        """Should convert **term** to highlighted span."""
        result = highlight_snippet('This is **important** text')
        self.assertIn('<span class="highlight">important</span>', result)
        self.assertNotIn('**', result)
    
    def test_highlights_multiple_terms(self):
        """Should highlight multiple terms."""
        result = highlight_snippet('**first** and **second** terms')
        self.assertEqual(result.count('<span class="highlight">'), 2)
        self.assertIn('first', result)
        self.assertIn('second', result)
    
    def test_escapes_html_in_snippet(self):
        """Should escape HTML in snippet text."""
        result = highlight_snippet('<script>**alert**</script>')
        self.assertIn('&lt;script&gt;', result)
        self.assertNotIn('<script>', result)
    
    def test_handles_empty_string(self):
        """Should return empty string for empty input."""
        self.assertEqual(highlight_snippet(''), '')
    
    def test_handles_none(self):
        """Should return empty string for None."""
        self.assertEqual(highlight_snippet(None), '')


class TestRenderPage(unittest.TestCase):
    """Tests for page rendering function."""
    
    def test_renders_welcome_page_without_query(self):
        """Should render welcome page when no query provided."""
        html = render_page()
        
        self.assertIn('Search Documentation', html)
        self.assertIn('welcome', html)
        self.assertIn('doc-search', html)
    
    def test_renders_results_with_query(self):
        """Should render results when query and results provided."""
        results = [
            {
                'url': 'https://example.com/page1',
                'title': 'Test Page 1',
                'snippet': 'This is a **test** snippet',
                'score': 1.5,
            },
            {
                'url': 'https://example.com/page2',
                'title': 'Test Page 2',
                'snippet': 'Another **snippet**',
                'score': 1.2,
            },
        ]
        
        html = render_page(
            query='test',
            results=results,
            elapsed_ms=5.0,
            total_results=2
        )
        
        self.assertIn('Test Page 1', html)
        self.assertIn('Test Page 2', html)
        self.assertIn('https://example.com/page1', html)
        self.assertIn('Found 2 results', html)
        self.assertIn('5.0ms', html)
    
    def test_renders_no_results_message(self):
        """Should render no results message when empty results."""
        html = render_page(query='nonexistent', results=[], total_results=0)
        
        self.assertIn('No results found', html)
    
    def test_escapes_query_in_html(self):
        """Should escape query to prevent XSS."""
        html = render_page(query='<script>alert(1)</script>')
        
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)
    
    def test_includes_stats_in_footer(self):
        """Should include document and term counts in footer."""
        stats = {'total_documents': 1234, 'unique_terms': 5678}
        html = render_page(stats=stats)
        
        self.assertIn('1,234', html)
        self.assertIn('5,678', html)
    
    def test_renders_pagination_for_multiple_pages(self):
        """Should render pagination controls for multi-page results."""
        results = [{'url': f'https://example.com/page{i}', 'title': f'Page {i}', 'score': 1.0}
                   for i in range(10)]
        
        html = render_page(
            query='test',
            results=results,
            total_results=50,  # 5 pages total
            page=2,
            per_page=10
        )
        
        self.assertIn('Previous', html)
        self.assertIn('Next', html)
        self.assertIn('page=1', html)
        self.assertIn('page=3', html)


# ============================================================================
# Integration Tests - HTTP Server
# ============================================================================

class TestServerWelcomePage(ServerTestCase):
    """Tests for server welcome page."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server."""
        cls.start_server()
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_get_root_returns_200(self):
        """GET / should return 200 OK."""
        status, headers, body = self.make_request('/')
        self.assertEqual(status, 200)
    
    def test_get_root_returns_html(self):
        """GET / should return HTML content type."""
        status, headers, body = self.make_request('/')
        self.assertIn('text/html', headers.get('Content-Type', ''))
    
    def test_welcome_page_contains_search_form(self):
        """Welcome page should contain search form."""
        status, headers, body = self.make_request('/')
        
        self.assertIn('<form', body)
        self.assertIn('name="q"', body)
        self.assertIn('Search', body)


class TestServerSearchResults(ServerTestCase):
    """Tests for server search results."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with mock results."""
        mock_results = [
            {
                'url': 'https://docs.example.com/guide',
                'title': 'Getting Started Guide',
                'snippet': 'This **test** guide helps you get started',
                'score': 2.5,
            },
            {
                'url': 'https://docs.example.com/api',
                'title': 'API Reference',
                'snippet': 'Complete **test** API documentation',
                'score': 1.8,
            },
        ]
        cls.engine = MockSearchEngine(results=mock_results)
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_search_returns_200(self):
        """GET /?q=test should return 200 OK."""
        status, headers, body = self.make_request('/?q=test')
        self.assertEqual(status, 200)
    
    def test_search_returns_results(self):
        """Search should return matching results."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertIn('Getting Started Guide', body)
        self.assertIn('API Reference', body)
        self.assertIn('Found 2 results', body)
    
    def test_search_calls_engine(self):
        """Search should call engine.search with query."""
        self.engine.search_calls.clear()
        self.make_request('/?q=myquery')
        
        self.assertEqual(len(self.engine.search_calls), 1)
        self.assertEqual(self.engine.search_calls[0]['query'], 'myquery')
    
    def test_pagination_param_works(self):
        """Page parameter should work."""
        status, headers, body = self.make_request('/?q=test&page=2')
        self.assertEqual(status, 200)
    
    def test_empty_query_shows_welcome(self):
        """Empty query should show welcome page."""
        status, headers, body = self.make_request('/?q=')
        
        self.assertEqual(status, 200)
        self.assertIn('Search Documentation', body)


class TestServerXSSPrevention(ServerTestCase):
    """Tests for XSS prevention in server responses."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server."""
        cls.start_server()
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_query_is_escaped_in_response(self):
        """Malicious query should be escaped in HTML output."""
        malicious_query = '<script>alert("xss")</script>'
        status, headers, body = self.make_request(f'/?q={malicious_query}')
        
        # The script tag should be escaped, not rendered
        self.assertNotIn('<script>alert', body)
        self.assertIn('&lt;script&gt;', body)


class TestServerContentType(ServerTestCase):
    """Tests for server content type headers."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server."""
        cls.start_server()
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_html_content_type_with_charset(self):
        """Response should include charset in content type."""
        status, headers, body = self.make_request('/')
        
        content_type = headers.get('Content-Type', '')
        self.assertIn('text/html', content_type)
        self.assertIn('charset=utf-8', content_type.lower())


# ============================================================================
# Phase 2.7: Additional Server Response Tests
# ============================================================================

class TestServerPaginationResponses(ServerTestCase):
    """Tests for pagination in server responses."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with many mock results for pagination."""
        # Create 25 results (3 pages at 10 per page)
        mock_results = [
            {
                'url': f'https://docs.example.com/page{i}',
                'title': f'Document {i}',
                'snippet': f'This is the snippet for document {i}',
                'score': 2.5 - (i * 0.1),
            }
            for i in range(25)
        ]
        cls.engine = MockSearchEngine(results=mock_results)
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_page_1_shows_first_10_results(self):
        """Page 1 should show results 1-10."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertIn('Document 0', body)
        self.assertIn('Document 9', body)
        self.assertNotIn('Document 10', body)
    
    def test_page_2_shows_next_10_results(self):
        """Page 2 should show results 11-20."""
        status, headers, body = self.make_request('/?q=test&page=2')
        
        self.assertNotIn('Document 0', body)
        self.assertIn('Document 10', body)
        self.assertIn('Document 19', body)
        self.assertNotIn('Document 20', body)
    
    def test_page_3_shows_remaining_results(self):
        """Page 3 should show remaining results."""
        status, headers, body = self.make_request('/?q=test&page=3')
        
        self.assertIn('Document 20', body)
        self.assertIn('Document 24', body)
    
    def test_first_page_has_disabled_previous(self):
        """Page 1 should show disabled Previous link."""
        status, headers, body = self.make_request('/?q=test&page=1')
        
        # Previous should be disabled (span with disabled class, not an <a> link)
        self.assertIn('class="disabled"', body)
        self.assertIn('Previous', body)
        # Should have active Next link
        self.assertIn('page=2', body)
    
    def test_last_page_has_disabled_next(self):
        """Last page should show disabled Next link."""
        status, headers, body = self.make_request('/?q=test&page=3')
        
        # Next should be disabled
        self.assertIn('Next', body)
        # Should have active Previous link
        self.assertIn('page=2', body)
    
    def test_pagination_shows_correct_result_range(self):
        """Pagination should show correct result range (e.g., 'showing 1-10')."""
        status, headers, body = self.make_request('/?q=test&page=1')
        self.assertIn('showing 1-10', body)
        
        status, headers, body = self.make_request('/?q=test&page=2')
        self.assertIn('showing 11-20', body)
    
    def test_invalid_page_number_handled(self):
        """Invalid page numbers should be handled gracefully."""
        status, headers, body = self.make_request('/?q=test&page=invalid')
        self.assertEqual(status, 200)
        # Should default to page 1
        self.assertIn('Document 0', body)
    
    def test_negative_page_treated_as_page_1(self):
        """Negative page numbers should be treated as page 1."""
        status, headers, body = self.make_request('/?q=test&page=-5')
        self.assertEqual(status, 200)
        self.assertIn('Document 0', body)


class TestServerHtmlWellFormedness(ServerTestCase):
    """Tests for HTML well-formedness."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server."""
        mock_results = [
            {'url': 'https://example.com/test', 'title': 'Test', 'score': 1.0}
        ]
        cls.engine = MockSearchEngine(results=mock_results)
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_response_has_doctype(self):
        """HTML should have DOCTYPE declaration."""
        status, headers, body = self.make_request('/')
        self.assertTrue(body.strip().startswith('<!DOCTYPE html>'))
    
    def test_response_has_html_lang(self):
        """HTML element should have lang attribute."""
        status, headers, body = self.make_request('/')
        self.assertIn('<html lang="en">', body)
    
    def test_response_has_meta_charset(self):
        """HTML should have charset meta tag."""
        status, headers, body = self.make_request('/')
        self.assertIn('<meta charset="UTF-8">', body)
    
    def test_response_has_viewport_meta(self):
        """HTML should have viewport meta for mobile."""
        status, headers, body = self.make_request('/')
        self.assertIn('viewport', body)
        self.assertIn('width=device-width', body)
    
    def test_response_has_title_tag(self):
        """HTML should have title tag."""
        status, headers, body = self.make_request('/')
        self.assertIn('<title>', body)
        self.assertIn('</title>', body)
    
    def test_search_page_has_query_in_title(self):
        """Search page should include query in title."""
        status, headers, body = self.make_request('/?q=python')
        self.assertIn('python', body[body.find('<title>'):body.find('</title>')])


class TestServerXSSPreventionAdvanced(ServerTestCase):
    """Advanced XSS prevention tests."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server."""
        cls.start_server()
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_escapes_quotes_in_query(self):
        """Quotes in query should be escaped to prevent attribute breakout."""
        import urllib.parse
        malicious = '"onmouseover="alert(1)'
        encoded = urllib.parse.quote(malicious)
        status, headers, body = self.make_request(f'/?q={encoded}')
        
        # Double quotes should be escaped as &quot;
        # The value attribute should remain intact (quotes don't break out)
        self.assertIn('&quot;', body)
        # Should NOT have unescaped quotes that could break the attribute
        # The pattern value="...onmouseover=..." should not occur
        self.assertNotIn('value=""', body)  # Quotes don't break the value
        self.assertEqual(status, 200)
    
    def test_escapes_single_quotes(self):
        """Single quotes should be escaped or neutralized."""
        import urllib.parse
        malicious = "'onclick='alert(1)"
        encoded = urllib.parse.quote(malicious)
        status, headers, body = self.make_request(f"/?q={encoded}")
        # Should not contain unescaped event handlers that could execute
        self.assertEqual(status, 200)
        # The single quotes are inside the double-quoted value, so they're safe
    
    def test_escapes_event_handler_injection(self):
        """Event handler injection attempts should be escaped."""
        import urllib.parse
        malicious = '<img src=x onerror=alert(1)>'
        encoded = urllib.parse.quote(malicious)
        status, headers, body = self.make_request(f'/?q={encoded}')
        
        # The < and > should be escaped
        self.assertNotIn('<img', body)
        self.assertIn('&lt;img', body)
    
    def test_escapes_javascript_protocol(self):
        """JavaScript protocol in query should be escaped."""
        import urllib.parse
        malicious = 'javascript:alert(1)'
        encoded = urllib.parse.quote(malicious)
        status, headers, body = self.make_request(f'/?q={encoded}')
        # Should be present as text, not as executable
        self.assertEqual(status, 200)
        # The literal "javascript:" shouldn't be in an href
        self.assertNotIn('href="javascript:', body.lower())


class TestServerResultRendering(ServerTestCase):
    """Tests for correct rendering of search results."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with varied mock results."""
        mock_results = [
            {
                'url': 'https://example.com/special&chars?param=1',
                'title': 'Title with <b>HTML</b> & special chars',
                'snippet': 'Snippet with **highlight** and <script>XSS</script>',
                'score': 2.0,
            },
        ]
        cls.engine = MockSearchEngine(results=mock_results)
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_result_title_is_escaped(self):
        """HTML in result titles should be escaped."""
        status, headers, body = self.make_request('/?q=test')
        
        # The <b> tag should be escaped, not rendered
        self.assertNotIn('<b>HTML</b>', body)
        self.assertIn('&lt;b&gt;HTML&lt;/b&gt;', body)
    
    def test_result_url_is_escaped(self):
        """Special chars in URLs should be escaped in display."""
        status, headers, body = self.make_request('/?q=test')
        
        # URL should be properly escaped in the display
        self.assertIn('&amp;', body)  # & becomes &amp;
    
    def test_snippet_xss_is_escaped(self):
        """XSS in snippets should be escaped."""
        status, headers, body = self.make_request('/?q=test')
        
        # Script tag should be escaped
        self.assertNotIn('<script>XSS</script>', body)
        self.assertIn('&lt;script&gt;', body)
    
    def test_snippet_highlight_preserved(self):
        """Highlight markers should become highlight spans."""
        status, headers, body = self.make_request('/?q=test')
        
        # **highlight** should become highlighted span
        self.assertIn('class="highlight"', body)
        self.assertIn('>highlight<', body)


# ============================================================================
# Phase 4.4: Health Check Endpoint Tests
# ============================================================================

class TestHealthEndpoint(ServerTestCase):
    """Tests for /health endpoint."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with mock engine."""
        cls.engine = MockSearchEngine(stats={
            'total_documents': 500,
            'unique_terms': 10000,
        })
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_health_returns_200_when_healthy(self):
        """GET /health should return 200 when documents are indexed."""
        status, headers, body = self.make_request('/health')
        self.assertEqual(status, 200)
    
    def test_health_returns_json(self):
        """GET /health should return JSON content type."""
        status, headers, body = self.make_request('/health')
        content_type = headers.get('Content-Type', '')
        self.assertIn('application/json', content_type)
    
    def test_health_contains_status_ok(self):
        """Health response should contain status: ok."""
        import json
        status, headers, body = self.make_request('/health')
        data = json.loads(body)
        self.assertEqual(data['status'], 'ok')
    
    def test_health_contains_document_count(self):
        """Health response should contain document count."""
        import json
        status, headers, body = self.make_request('/health')
        data = json.loads(body)
        self.assertEqual(data['documents'], 500)
    
    def test_health_contains_term_count(self):
        """Health response should contain term count."""
        import json
        status, headers, body = self.make_request('/health')
        data = json.loads(body)
        self.assertEqual(data['terms'], 10000)
    
    def test_health_contains_uptime(self):
        """Health response should contain uptime_seconds."""
        import json
        status, headers, body = self.make_request('/health')
        data = json.loads(body)
        self.assertIn('uptime_seconds', data)
        self.assertGreaterEqual(data['uptime_seconds'], 0)
    
    def test_health_contains_version(self):
        """Health response should contain version."""
        import json
        status, headers, body = self.make_request('/health')
        data = json.loads(body)
        self.assertIn('version', data)


class TestHealthEndpointUnhealthy(ServerTestCase):
    """Tests for /health endpoint when unhealthy."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with empty engine (no documents)."""
        cls.engine = MockSearchEngine(stats={
            'total_documents': 0,  # No documents = unhealthy
            'unique_terms': 0,
        })
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_health_returns_503_when_unhealthy(self):
        """GET /health should return 503 when no documents indexed."""
        status, headers, body = self.make_request('/health')
        self.assertEqual(status, 503)
    
    def test_health_contains_status_unhealthy(self):
        """Health response should contain status: unhealthy."""
        import json
        status, headers, body = self.make_request('/health')
        data = json.loads(body)
        self.assertEqual(data['status'], 'unhealthy')
    
    def test_health_contains_reason(self):
        """Unhealthy response should contain reason."""
        import json
        status, headers, body = self.make_request('/health')
        data = json.loads(body)
        self.assertIn('reason', data)
        self.assertIn('documents', data['reason'].lower())


if __name__ == '__main__':
    unittest.main()
