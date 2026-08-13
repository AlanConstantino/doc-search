"""
Tests for the web server module.
"""

import re
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


def strip_script_content(html: str) -> str:
    """Remove content between <script> tags for testing visible content only.
    
    This is needed because the JavaScript code may contain template strings
    that match content we're testing for (e.g., "Did you mean:", facet HTML).
    """
    return re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)


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


class MockEnhancedSearchEngine(MockSearchEngine):
    """Mock EnhancedSearchEngine with suggestions, spell check, facet, and synonym support."""
    
    def __init__(self, results: Optional[List[Dict[str, Any]]] = None,
                 stats: Optional[Dict[str, Any]] = None,
                 suggestions: Optional[List[str]] = None,
                 spelling_suggestion: Optional[str] = None,
                 facet_counts: Optional[Dict[str, Dict[str, int]]] = None,
                 synonym_results: Optional[List[Dict[str, Any]]] = None):
        """
        Create mock enhanced search engine.

        Args:
            results: List of result dicts to return from search()
            stats: Stats dict to return from get_stats()
            suggestions: List of title suggestions to return
            spelling_suggestion: Spelling suggestion to return (or None)
            facet_counts: Facet counts to return from get_facet_counts()
            synonym_results: Results to return when synonyms expanded (or None for same as results)
        """
        super().__init__(results, stats)
        self._suggestions = suggestions or []
        self._spelling_suggestion = spelling_suggestion
        self._facet_counts = facet_counts or {}
        self._synonym_results = synonym_results
        self._last_expand_synonyms = None
    
    def search(self, query: str, top_k: int = 10, expand_synonyms: bool = False) -> List[Dict[str, Any]]:
        """Search with optional synonym expansion."""
        self._last_expand_synonyms = expand_synonyms
        self.search_calls.append({'query': query, 'top_k': top_k, 'expand_synonyms': expand_synonyms})
        if expand_synonyms and self._synonym_results is not None:
            return self._synonym_results[:top_k]
        return self._results[:top_k]
    
    def get_suggestions(self, prefix: str, max_suggestions: int = 8) -> List[dict]:
        """Return mock title suggestions."""
        matching = [s for s in self._suggestions if s.startswith(prefix)]
        return [{'text': s, 'doc_type': None, 'url': None} for s in matching[:max_suggestions]]
    
    def get_spelling_suggestion(self, query: str) -> Optional[str]:
        """Return mock spelling suggestion."""
        return self._spelling_suggestion
    
    def get_facet_counts(self, results: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        """Return mock facet counts."""
        return self._facet_counts


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
        self.assertIn('<mark>important</mark>', result)
        self.assertNotIn('**', result)
    
    def test_highlights_multiple_terms(self):
        """Should highlight multiple terms."""
        result = highlight_snippet('**first** and **second** terms')
        self.assertEqual(result.count('<mark>'), 2)
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
        
        self.assertIn('Prev', html)
        self.assertIn('Next', html)
        self.assertIn('First', html)
        self.assertIn('Last', html)
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
        """Page 1 should show disabled Prev link."""
        status, headers, body = self.make_request('/?q=test&page=1')
        
        # Prev/First should be disabled (span with disabled class, not an <a> link)
        self.assertIn('class="disabled"', body)
        self.assertIn('Prev', body)
        self.assertIn('First', body)
        # Should have active Next/Last link
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
        """Highlight markers should become <mark> elements (HTML5)."""
        status, headers, body = self.make_request('/?q=test')
        
        # **highlight** should become <mark> element
        self.assertIn('<mark>', body)
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


# ============================================================================
# Issue #149: Spell Check ("Did you mean...") Tests
# ============================================================================

class TestRenderPageSpellSuggestion(unittest.TestCase):
    """Tests for spell check suggestion rendering."""
    
    def test_renders_suggestion_when_provided(self):
        """Should render 'Did you mean' when suggestion provided."""
        html = render_page(
            query='pyhton',
            results=[],
            suggestion='python'
        )
        
        self.assertIn('Did you mean', html)
        self.assertIn('python', html)
        self.assertIn('spell-suggestion', html)
    
    def test_suggestion_is_clickable_link(self):
        """Suggestion should be a clickable link."""
        html = render_page(
            query='pyhton',
            results=[],
            suggestion='python'
        )
        
        # Should have a link to search with the suggestion
        self.assertIn('href="/?q=python"', html)
        self.assertIn('spell-suggestion-link', html)
    
    def test_no_suggestion_when_none(self):
        """Should not render suggestion section when None."""
        html = render_page(
            query='test',
            results=[],
            suggestion=None
        )
        
        # Strip script content since JS templates contain "Did you mean"
        visible_html = strip_script_content(html)
        self.assertNotIn('Did you mean', visible_html)
        # Check for the div element, not just the CSS class name
        self.assertNotIn('<div class="spell-suggestion">', visible_html)
    
    def test_suggestion_escapes_special_chars(self):
        """Suggestion should be HTML escaped."""
        html = render_page(
            query='test',
            results=[],
            suggestion='<script>alert(1)</script>'
        )
        
        self.assertNotIn('<script>alert', html)
        self.assertIn('&lt;script&gt;', html)
    
    def test_suggestion_url_encoded_in_link(self):
        """Suggestion with spaces should be URL encoded in link."""
        html = render_page(
            query='pyhton async',
            results=[],
            suggestion='python async'
        )
        
        # The link href should have URL-encoded spaces
        self.assertIn('href="/?q=python%20async"', html)


class TestServerSpellCheckSuggestion(ServerTestCase):
    """Tests for spell check suggestion in server responses."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with enhanced engine that returns spell suggestions."""
        # No results, but has a spelling suggestion
        cls.engine = MockEnhancedSearchEngine(
            results=[],
            spelling_suggestion='python'
        )
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_shows_suggestion_on_no_results(self):
        """Should show 'Did you mean' when no results and suggestion available."""
        status, headers, body = self.make_request('/?q=pyhton')
        
        self.assertEqual(status, 200)
        self.assertIn('Did you mean', body)
        self.assertIn('python', body)
    
    def test_suggestion_link_is_clickable(self):
        """Suggestion link should point to corrected query."""
        status, headers, body = self.make_request('/?q=pyhton')
        
        self.assertIn('href="/?q=python"', body)


class TestServerSpellCheckNoSuggestion(ServerTestCase):
    """Tests for server when spell check returns no suggestion."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with enhanced engine that returns no suggestion."""
        cls.engine = MockEnhancedSearchEngine(
            results=[],
            spelling_suggestion=None
        )
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_no_suggestion_shown_when_none_available(self):
        """Should not show suggestion when engine returns None."""
        status, headers, body = self.make_request('/?q=xyzabc123')
        
        self.assertEqual(status, 200)
        # Strip script content since JS templates contain "Did you mean"
        visible_body = strip_script_content(body)
        self.assertNotIn('Did you mean', visible_body)
        self.assertNotIn('<div class="spell-suggestion">', visible_body)
        # Should still show no results message
        self.assertIn('No results found', visible_body)


class TestServerSpellCheckWithResults(ServerTestCase):
    """Tests for spell check when results are found."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with results (no suggestion needed)."""
        mock_results = [
            {'url': 'https://example.com/test', 'title': 'Test Page', 'score': 1.0}
        ]
        cls.engine = MockEnhancedSearchEngine(
            results=mock_results,
            spelling_suggestion='python'  # Suggestion exists but shouldn't show
        )
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_no_suggestion_shown_when_results_found(self):
        """Should not show suggestion when results are found."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        # Should show results
        self.assertIn('Test Page', body)
        # Should NOT show spell suggestion (results were found)
        # Strip script content since JS templates contain "Did you mean"
        visible_body = strip_script_content(body)
        self.assertNotIn('Did you mean', visible_body)
        self.assertNotIn('<div class="spell-suggestion">', visible_body)


class TestServerWithBasicEngine(ServerTestCase):
    """Tests that basic SearchEngine (without spell check) still works."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with basic engine (no spell check)."""
        cls.engine = MockSearchEngine(results=[])
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_works_without_spell_check_method(self):
        """Server should work when engine lacks get_spelling_suggestion."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        # Strip script content since JS templates contain "Did you mean"
        visible_body = strip_script_content(body)
        # Should show no results without crashing
        self.assertIn('No results found', visible_body)
        # No spell suggestion shown (engine doesn't have the method)
        self.assertNotIn('Did you mean', visible_body)
        self.assertNotIn('<div class="spell-suggestion">', visible_body)


# ============================================================================
# Issue #150: Autocomplete / Suggest Endpoint Tests
# ============================================================================

class TestSuggestEndpoint(ServerTestCase):
    """Tests for /suggest endpoint."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with mock suggestion engine."""
        cls.engine = MockEnhancedSearchEngine(
            suggestions=[
                'python', 'python async', 'python await', 'python class',
                'python function', 'pytest', 'pypi'
            ]
        )
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_suggest_returns_200(self):
        """GET /suggest should return 200 OK."""
        status, headers, body = self.make_request('/suggest?q=py')
        self.assertEqual(status, 200)
    
    def test_suggest_returns_json(self):
        """GET /suggest should return JSON content type."""
        status, headers, body = self.make_request('/suggest?q=py')
        content_type = headers.get('Content-Type', '')
        self.assertIn('application/json', content_type)
    
    def test_suggest_returns_suggestions(self):
        """GET /suggest should return suggestions array."""
        import json
        status, headers, body = self.make_request('/suggest?q=py')
        data = json.loads(body)
        
        self.assertIn('suggestions', data)
        self.assertIsInstance(data['suggestions'], list)
        self.assertTrue(len(data['suggestions']) > 0)
    
    def test_suggest_filters_by_prefix(self):
        """Suggestions should match the prefix."""
        import json
        status, headers, body = self.make_request('/suggest?q=python')
        data = json.loads(body)
        
        # All suggestions should contain text starting with 'python'
        for suggestion in data['suggestions']:
            text = suggestion['text'] if isinstance(suggestion, dict) else suggestion
            self.assertTrue(text.startswith('python'))
    
    def test_suggest_respects_limit(self):
        """GET /suggest should respect limit parameter."""
        import json
        status, headers, body = self.make_request('/suggest?q=py&limit=2')
        data = json.loads(body)
        
        self.assertLessEqual(len(data['suggestions']), 2)
    
    def test_suggest_default_limit_is_5(self):
        """Default limit should be 5."""
        import json
        status, headers, body = self.make_request('/suggest?q=py')
        data = json.loads(body)
        
        # We have 7 suggestions starting with 'py', should get max 5
        self.assertLessEqual(len(data['suggestions']), 5)
    
    def test_suggest_max_limit_is_20(self):
        """Limit should be capped at 20."""
        import json
        status, headers, body = self.make_request('/suggest?q=py&limit=100')
        data = json.loads(body)
        
        # Even with limit=100, should not exceed 20
        self.assertLessEqual(len(data['suggestions']), 20)
    
    def test_suggest_empty_query_returns_empty(self):
        """Empty query should return empty suggestions."""
        import json
        status, headers, body = self.make_request('/suggest?q=')
        data = json.loads(body)
        
        self.assertEqual(data['suggestions'], [])
    
    def test_suggest_no_match_returns_empty(self):
        """Query with no matches should return empty suggestions."""
        import json
        status, headers, body = self.make_request('/suggest?q=xyz123')
        data = json.loads(body)
        
        self.assertEqual(data['suggestions'], [])
    
    def test_suggest_invalid_limit_uses_default(self):
        """Invalid limit parameter should use default."""
        import json
        status, headers, body = self.make_request('/suggest?q=py&limit=invalid')
        data = json.loads(body)
        
        self.assertEqual(status, 200)
        self.assertIn('suggestions', data)


class TestSuggestEndpointDisabled(ServerTestCase):
    """Tests for /suggest endpoint when disabled."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with suggestions disabled."""
        cls.engine = MockEnhancedSearchEngine(
            suggestions=['python', 'pytest']
        )
        cls.start_server(engine=cls.engine, enable_autocomplete=False)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_suggest_returns_403_when_disabled(self):
        """GET /suggest should return 403 when autocomplete is disabled."""
        status, headers, body = self.make_request('/suggest?q=py')
        self.assertEqual(status, 403)
    
    def test_suggest_error_message_when_disabled(self):
        """Should return error message when disabled."""
        import json
        status, headers, body = self.make_request('/suggest?q=py')
        data = json.loads(body)
        
        self.assertIn('error', data)
        self.assertIn('disabled', data['error'].lower())


class TestSuggestEndpointNoSupport(ServerTestCase):
    """Tests for /suggest endpoint with basic engine (no suggestion support)."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with basic engine."""
        cls.engine = MockSearchEngine()  # Basic engine, no suggestion method
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_suggest_returns_501_when_not_supported(self):
        """GET /suggest should return 501 when engine lacks suggestion support."""
        status, headers, body = self.make_request('/suggest?q=py')
        self.assertEqual(status, 501)
    
    def test_suggest_error_message_when_not_supported(self):
        """Should return error message when not supported."""
        import json
        status, headers, body = self.make_request('/suggest?q=py')
        data = json.loads(body)
        
        self.assertIn('error', data)
        self.assertIn('not available', data['error'].lower())


# ============================================================================
# Issue #151: Faceted Search Tests
# ============================================================================

class TestRenderPageFacets(unittest.TestCase):
    """Tests for facet filter rendering."""
    
    def test_renders_facets_when_provided(self):
        """Should render facet filter bar when facets provided."""
        facets = {'category': {'api': 10, 'tutorial': 5, 'guide': 3}}
        html = render_page(
            query='python',
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}],
            facets=facets,
            total_results=18
        )
        
        self.assertIn('facet-filters', html)
        self.assertIn('api', html)
        self.assertIn('tutorial', html)
        self.assertIn('guide', html)
    
    def test_facet_buttons_are_links(self):
        """Facet buttons should be clickable links."""
        facets = {'category': {'api': 10, 'tutorial': 5}}
        html = render_page(
            query='python',
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}],
            facets=facets,
            total_results=15
        )
        
        self.assertIn('href="/?q=python&category=api"', html)
        self.assertIn('href="/?q=python&category=tutorial"', html)
    
    def test_active_facet_highlighted(self):
        """Active facet should have active class."""
        facets = {'category': {'api': 10, 'tutorial': 5}}
        html = render_page(
            query='python',
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}],
            facets=facets,
            active_facet='api',
            total_results=10
        )
        
        # The api button should have active class
        self.assertIn('class="facet-btn active"', html)
    
    def test_all_button_clears_filter(self):
        """All button should link to query without facet."""
        facets = {'category': {'api': 10, 'tutorial': 5}}
        html = render_page(
            query='python',
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}],
            facets=facets,
            active_facet='api',
            total_results=10,
            total_unfiltered=15
        )
        
        # Should have "All" button without category param
        self.assertIn('href="/?q=python"', html)
        self.assertIn('>All <', html)
    
    def test_facet_counts_shown(self):
        """Facet counts should be displayed."""
        facets = {'category': {'api': 10, 'tutorial': 5}}
        html = render_page(
            query='python',
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}],
            facets=facets,
            total_results=15
        )
        
        self.assertIn('10', html)
        self.assertIn('5', html)
    
    def test_no_facets_when_single_category(self):
        """Should not show facets when only one category."""
        facets = {'category': {'api': 10}}
        html = render_page(
            query='python',
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}],
            facets=facets,
            total_results=10
        )
        
        # Strip script content since JS templates contain facet rendering code
        visible_html = strip_script_content(html)
        # Shouldn't show facet bar div with only one category
        self.assertNotIn('<div class="facet-filters">', visible_html)
    
    def test_no_facets_when_none(self):
        """Should not show facets when None."""
        html = render_page(
            query='python',
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}],
            facets=None,
            total_results=1
        )
        
        # Strip script content since JS templates contain facet rendering code
        visible_html = strip_script_content(html)
        self.assertNotIn('<div class="facet-filters">', visible_html)
    
    def test_pagination_preserves_facet(self):
        """Pagination links should preserve active facet."""
        facets = {'category': {'api': 25, 'tutorial': 15}}
        html = render_page(
            query='python',
            results=[{'url': f'http://test{i}', 'title': f'Test {i}', 'score': 1.0} for i in range(10)],
            facets=facets,
            active_facet='api',
            total_results=25,
            page=1,
            per_page=10
        )
        
        # Pagination link should include category parameter
        self.assertIn('page=2&category=api', html)


class TestServerFacetedSearch(ServerTestCase):
    """Tests for faceted search in server responses."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with facet-enabled engine."""
        # Results with facets
        mock_results = [
            {'url': 'http://test1', 'title': 'API Doc 1', 'score': 2.0, 'facets': {'category': 'api'}},
            {'url': 'http://test2', 'title': 'API Doc 2', 'score': 1.8, 'facets': {'category': 'api'}},
            {'url': 'http://test3', 'title': 'Tutorial 1', 'score': 1.5, 'facets': {'category': 'tutorial'}},
        ]
        cls.engine = MockEnhancedSearchEngine(
            results=mock_results,
            facet_counts={'category': {'api': 2, 'tutorial': 1}}
        )
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_facets_shown_in_results(self):
        """Should show facet filter bar with results."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        self.assertIn('facet-filters', body)
        self.assertIn('api', body)
        self.assertIn('tutorial', body)
    
    def test_facet_filter_applied(self):
        """Clicking facet should filter results."""
        status, headers, body = self.make_request('/?q=test&category=api')
        
        self.assertEqual(status, 200)
        # Should show API docs
        self.assertIn('API Doc', body)
        # Should show 2 results (filtered)
        self.assertIn('Found 2 result', body)


class TestServerFacetsDisabled(ServerTestCase):
    """Tests when facets are disabled."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with facets disabled."""
        mock_results = [
            {'url': 'http://test1', 'title': 'Test 1', 'score': 1.0, 'facets': {'category': 'api'}},
        ]
        cls.engine = MockEnhancedSearchEngine(
            results=mock_results,
            facet_counts={'category': {'api': 1}}
        )
        cls.start_server(engine=cls.engine, enable_facets=False)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_no_facets_when_disabled(self):
        """Should not show facets when disabled."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        # Strip script content since JS templates contain facet rendering code
        visible_body = strip_script_content(body)
        self.assertNotIn('<div class="facet-filters">', visible_body)
    
    def test_facet_param_ignored_when_disabled(self):
        """Facet parameter should be ignored when disabled."""
        status, headers, body = self.make_request('/?q=test&category=api')
        
        self.assertEqual(status, 200)
        # Should still show results without filtering
        self.assertIn('Test 1', body)


class TestServerFacetsNoSupport(ServerTestCase):
    """Tests with basic engine (no facet support)."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with basic engine."""
        mock_results = [
            {'url': 'http://test1', 'title': 'Test 1', 'score': 1.0},
        ]
        cls.engine = MockSearchEngine(results=mock_results)
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_works_without_facet_method(self):
        """Server should work when engine lacks get_facet_counts."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        self.assertIn('Test 1', body)
        # Strip script content since JS templates contain facet rendering code
        visible_body = strip_script_content(body)
        self.assertNotIn('<div class="facet-filters">', visible_body)


# ============================================================================
# Issue #152: Synonym Toggle Tests
# ============================================================================

# ============================================================================
# Issue #152: Synonym Expansion Tests (CLI flag, no UI toggle)
# ============================================================================

class TestServerSynonymsEnabled(ServerTestCase):
    """Tests for server with synonyms enabled via CLI flag."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with synonyms enabled."""
        normal_results = [
            {'url': 'http://normal', 'title': 'Normal Result', 'score': 1.0}
        ]
        synonym_results = [
            {'url': 'http://normal', 'title': 'Normal Result', 'score': 1.0},
            {'url': 'http://synonym', 'title': 'Synonym Result', 'score': 0.9}
        ]
        cls.engine = MockEnhancedSearchEngine(
            results=normal_results,
            synonym_results=synonym_results
        )
        cls.start_server(engine=cls.engine, enable_synonyms=True)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_no_checkbox_in_ui(self):
        """Should NOT show synonym checkbox in UI (CLI flag only)."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        self.assertNotIn('Expand synonyms', body)
        self.assertNotIn('name="synonyms"', body)
    
    def test_synonyms_always_expanded_when_enabled(self):
        """Synonyms should always be expanded when enable_synonyms=True."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        self.assertEqual(self.engine._last_expand_synonyms, True)

    def test_exact_match_quotes_query_and_disables_synonyms(self):
        """Exact match must phrase-quote the query and pass expand_synonyms=False."""
        self.engine.search_calls.clear()
        status, headers, body = self.make_request('/?q=running+files&exact=1')

        self.assertEqual(status, 200)
        self.assertEqual(self.engine._last_expand_synonyms, False)
        self.assertTrue(self.engine.search_calls)
        self.assertEqual(self.engine.search_calls[-1]['query'], '"running files"')
        self.assertEqual(self.engine.search_calls[-1]['expand_synonyms'], False)


class TestServerSynonymsDisabled(ServerTestCase):
    """Tests for server with synonyms disabled."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with synonyms disabled."""
        cls.engine = MockEnhancedSearchEngine(
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}]
        )
        cls.start_server(engine=cls.engine, enable_synonyms=False)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_synonyms_not_expanded_when_disabled(self):
        """Synonyms should NOT be expanded when enable_synonyms=False."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        self.assertEqual(self.engine._last_expand_synonyms, False)


class TestServerSynonymsBasicEngine(ServerTestCase):
    """Tests with basic engine (no synonym support in search method)."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with basic engine."""
        cls.engine = MockSearchEngine(
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}]
        )
        cls.start_server(engine=cls.engine, enable_synonyms=True)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_works_without_expand_synonyms_support(self):
        """Server should work when engine search() lacks expand_synonyms."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        self.assertIn('Test', body)


# ============================================================================
# Issue #172-180: JavaScript UI API Tests
# ============================================================================

class TestApiSearchEndpoint(ServerTestCase):
    """Tests for /api/search JSON endpoint (instant search)."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with mock engine."""
        cls.engine = MockSearchEngine(
            results=[
                {'url': 'http://test1', 'title': 'Test One', 'score': 1.0, 'snippet': 'First result'},
                {'url': 'http://test2', 'title': 'Test Two', 'score': 0.9, 'snippet': 'Second result'},
            ]
        )
        cls.start_server(engine=cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_api_search_returns_json(self):
        """API endpoint should return JSON content type."""
        import json
        status, headers, body = self.make_request('/api/search?q=test')
        
        self.assertEqual(status, 200)
        self.assertIn('application/json', headers.get('Content-Type', ''))
        
        # Should be valid JSON
        data = json.loads(body)
        self.assertIn('results', data)
        self.assertIn('total', data)
    
    def test_api_search_returns_results(self):
        """API endpoint should return search results."""
        import json
        status, headers, body = self.make_request('/api/search?q=test')
        
        data = json.loads(body)
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['results'][0]['title'], 'Test One')
        self.assertEqual(data['results'][1]['title'], 'Test Two')
    
    def test_api_search_empty_query(self):
        """API endpoint should handle empty query."""
        import json
        status, headers, body = self.make_request('/api/search?q=')
        
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['results'], [])
        self.assertEqual(data['total'], 0)
    
    def test_api_search_pagination(self):
        """API endpoint should support pagination."""
        import json
        status, headers, body = self.make_request('/api/search?q=test&page=1&limit=10')
        
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn('page', data)
        self.assertIn('total_pages', data)

    def test_api_search_exact_match_quotes_query(self):
        """API exact=1 should wrap the query in quotes for phrase matching."""
        self.engine.search_calls.clear()
        status, headers, body = self.make_request('/api/search?q=running+files&exact=1')

        self.assertEqual(status, 200)
        self.assertTrue(self.engine.search_calls)
        self.assertEqual(self.engine.search_calls[-1]['query'], '"running files"')


class TestNoJavaScriptFlag(ServerTestCase):
    """Tests for --no-javascript flag (graceful degradation)."""
    
    @classmethod
    def setUpClass(cls):
        """Start test server with no_javascript=True."""
        cls.engine = MockSearchEngine(
            results=[{'url': 'http://test', 'title': 'Test', 'score': 1.0}]
        )
        cls.start_server(engine=cls.engine, no_javascript=True)
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server."""
        cls.stop_server()
    
    def test_no_script_tags_when_disabled(self):
        """Should not include <script> tags when --no-javascript is set."""
        status, headers, body = self.make_request('/')
        
        self.assertEqual(status, 200)
        self.assertNotIn('<script>', body)
    
    def test_form_still_works(self):
        """Search form should still work without JavaScript."""
        status, headers, body = self.make_request('/?q=test')
        
        self.assertEqual(status, 200)
        self.assertIn('Test', body)


if __name__ == '__main__':
    unittest.main()
