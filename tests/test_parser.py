"""
Tests for HTML parsing and link extraction.
"""

import unittest
from unittest.mock import patch, MagicMock
from doc_search.parser import extract_text, extract_links, HTMLTextExtractor


class TestExtractText(unittest.TestCase):
    """Tests for HTML text extraction."""
    
    def test_basic_extraction(self):
        """Should extract text from basic HTML."""
        html = '<html><body><p>Hello World</p></body></html>'
        result = extract_text(html)
        self.assertIn('Hello World', result['text'])
    
    def test_extract_title(self):
        """Should extract title from HTML."""
        html = '<html><head><title>Page Title</title></head><body>Content</body></html>'
        result = extract_text(html)
        self.assertEqual(result['title'], 'Page Title')
    
    def test_extract_description(self):
        """Should extract meta description."""
        html = '<html><head><meta name="description" content="Page description"></head></html>'
        result = extract_text(html)
        self.assertEqual(result['description'], 'Page description')
    
    def test_removes_script(self):
        """Should remove script content."""
        html = '<script>alert("bad")</script><p>Good content</p>'
        result = extract_text(html)
        self.assertNotIn('alert', result['text'])
        self.assertIn('Good content', result['text'])
    
    def test_removes_style(self):
        """Should remove style content."""
        html = '<style>.class { color: red; }</style><p>Good content</p>'
        result = extract_text(html)
        self.assertNotIn('color', result['text'])
        self.assertIn('Good content', result['text'])
    
    def test_removes_nav(self):
        """Should remove navigation content by default."""
        html = '<nav>Navigation</nav><p>Main content</p>'
        result = extract_text(html)
        self.assertNotIn('Navigation', result['text'])
        self.assertIn('Main content', result['text'])
    
    def test_empty_html(self):
        """Should handle empty HTML."""
        result = extract_text('')
        self.assertEqual(result['text'], '')
        self.assertEqual(result['title'], '')
    
    def test_malformed_html(self):
        """Should handle malformed HTML gracefully."""
        html = '<p>Unclosed paragraph<div>Mixed tags</p></div>'
        result = extract_text(html)
        # Should not crash, and should extract some text
        self.assertIn('Unclosed paragraph', result['text'])
    
    def test_non_string_input_returns_empty(self):
        """Should handle non-string input (TypeError) gracefully."""
        # Passing None or other non-string types should not crash
        result = extract_text(None)  # type: ignore
        self.assertEqual(result['text'], '')
        self.assertEqual(result['title'], '')
        
        result = extract_text(123)  # type: ignore
        self.assertEqual(result['text'], '')
        self.assertEqual(result['title'], '')
        
        result = extract_text(['<p>list</p>'])  # type: ignore
        self.assertEqual(result['text'], '')
        self.assertEqual(result['title'], '')
    
    def test_assertion_error_returns_partial(self):
        """Should handle AssertionError gracefully and return partial results."""
        with patch.object(HTMLTextExtractor, 'feed') as mock_feed:
            mock_feed.side_effect = AssertionError("Internal assertion failure")
            result = extract_text('<p>Content</p>')
            # Should return empty/default structure without crashing
            self.assertIn('text', result)
            self.assertIn('title', result)
            self.assertEqual(result['text'], '')
    
    def test_unhandled_exceptions_propagate(self):
        """Verify that unexpected exceptions are not silently swallowed."""
        with patch.object(HTMLTextExtractor, 'feed') as mock_feed:
            # ValueError should NOT be caught - it should propagate
            mock_feed.side_effect = ValueError("Unexpected error")
            with self.assertRaises(ValueError):
                extract_text('<p>Content</p>')


class TestExtractLinks(unittest.TestCase):
    """Tests for link extraction."""
    
    def test_basic_link(self):
        """Should extract basic link."""
        html = '<a href="page.html">Link</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertEqual(links, ['http://example.com/page.html'])
    
    def test_double_quoted_href(self):
        """Should extract double-quoted href."""
        html = '<a href="page.html">Link</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertIn('http://example.com/page.html', links)
    
    def test_single_quoted_href(self):
        """Should extract single-quoted href."""
        html = "<a href='page.html'>Link</a>"
        links = extract_links(html, 'http://example.com/')
        self.assertIn('http://example.com/page.html', links)
    
    def test_unquoted_href(self):
        """Should extract unquoted href."""
        html = '<a href=page.html>Link</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertIn('http://example.com/page.html', links)
    
    def test_uppercase_href(self):
        """Should handle uppercase HREF attribute."""
        html = '<A HREF=page.html>Link</A>'
        links = extract_links(html, 'http://example.com/')
        self.assertIn('http://example.com/page.html', links)
    
    def test_multiple_links(self):
        """Should extract multiple links."""
        html = '<a href="one.html">One</a><a href=two.html>Two</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertEqual(len(links), 2)
        self.assertIn('http://example.com/one.html', links)
        self.assertIn('http://example.com/two.html', links)
    
    def test_skip_javascript(self):
        """Should skip javascript: links."""
        html = '<a href="javascript:alert(1)">Bad</a><a href="good.html">Good</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertEqual(links, ['http://example.com/good.html'])
    
    def test_skip_mailto(self):
        """Should skip mailto: links."""
        html = '<a href="mailto:test@test.com">Email</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertEqual(links, [])
    
    def test_skip_anchor(self):
        """Should skip anchor links."""
        html = '<a href="#section">Anchor</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertEqual(links, [])
    
    def test_resolve_relative_url(self):
        """Should resolve relative URLs."""
        html = '<a href="../other/page.html">Link</a>'
        links = extract_links(html, 'http://example.com/docs/current/')
        self.assertIn('http://example.com/docs/other/page.html', links)
    
    def test_absolute_url(self):
        """Should handle absolute URLs."""
        html = '<a href="http://other.com/page.html">Link</a>'
        links = extract_links(html, 'http://example.com/')
        self.assertIn('http://other.com/page.html', links)


if __name__ == '__main__':
    unittest.main()
