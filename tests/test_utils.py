"""
Tests for utility functions including URL normalization.
"""

import unittest
from doc_search.utils import normalize_url, tokenize, is_valid_url, get_domain


class TestNormalizeUrl(unittest.TestCase):
    """Tests for URL normalization."""
    
    def test_lowercase_scheme_and_host(self):
        """Should lowercase scheme and host."""
        self.assertEqual(
            normalize_url("HTTP://EXAMPLE.COM/Path"),
            "http://example.com/Path"
        )
    
    def test_remove_default_port_http(self):
        """Should remove default port 80 for http."""
        self.assertEqual(
            normalize_url("http://example.com:80/path"),
            "http://example.com/path"
        )
    
    def test_remove_default_port_https(self):
        """Should remove default port 443 for https."""
        self.assertEqual(
            normalize_url("https://example.com:443/path"),
            "https://example.com/path"
        )
    
    def test_keep_non_default_port(self):
        """Should keep non-default ports."""
        self.assertEqual(
            normalize_url("http://example.com:8080/path"),
            "http://example.com:8080/path"
        )
    
    def test_remove_fragment(self):
        """Should remove URL fragments."""
        self.assertEqual(
            normalize_url("http://example.com/path#section"),
            "http://example.com/path"
        )
    
    def test_sort_query_params(self):
        """Should sort query parameters."""
        self.assertEqual(
            normalize_url("http://example.com/path?b=2&a=1"),
            "http://example.com/path?a=1&b=2"
        )
    
    def test_resolve_dotdot(self):
        """Should resolve .. in path."""
        self.assertEqual(
            normalize_url("http://example.com/a/../b"),
            "http://example.com/b"
        )
    
    def test_resolve_dot(self):
        """Should resolve . in path."""
        self.assertEqual(
            normalize_url("http://example.com/./a"),
            "http://example.com/a"
        )
    
    def test_resolve_complex_path(self):
        """Should resolve complex path with multiple .. and ."""
        self.assertEqual(
            normalize_url("http://example.com/a/b/../c/../d"),
            "http://example.com/a/d"
        )
    
    def test_preserve_trailing_slash_directory(self):
        """Should preserve trailing slash for directory-like paths."""
        self.assertEqual(
            normalize_url("http://example.com/path/"),
            "http://example.com/path/"
        )
    
    def test_remove_trailing_slash_file(self):
        """Should remove trailing slash for file-like paths."""
        self.assertEqual(
            normalize_url("http://example.com/page.html/"),
            "http://example.com/page.html"
        )
    
    def test_root_path(self):
        """Should handle root path correctly."""
        self.assertEqual(
            normalize_url("http://example.com/"),
            "http://example.com/"
        )
    
    def test_no_path(self):
        """Should handle URL with no path."""
        self.assertEqual(
            normalize_url("http://example.com"),
            "http://example.com/"
        )


class TestTokenize(unittest.TestCase):
    """Tests for tokenization."""
    
    def test_basic_tokenization(self):
        """Should tokenize basic text."""
        tokens = tokenize("Hello World")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)
    
    def test_removes_stopwords(self):
        """Should remove stop words."""
        tokens = tokenize("the quick brown fox")
        self.assertNotIn("the", tokens)
        self.assertIn("quick", tokens)
    
    def test_removes_short_words(self):
        """Should remove single-character words."""
        tokens = tokenize("a b c test")
        self.assertNotIn("a", tokens)
        self.assertNotIn("b", tokens)
        self.assertIn("test", tokens)
    
    def test_empty_string(self):
        """Should return empty list for empty string."""
        self.assertEqual(tokenize(""), [])
    
    def test_whitespace_only(self):
        """Should return empty list for whitespace only."""
        self.assertEqual(tokenize("   "), [])
    
    def test_preserves_underscores(self):
        """Should preserve underscores in identifiers."""
        tokens = tokenize("snake_case variable")
        self.assertIn("snake_case", tokens)


class TestGetDomain(unittest.TestCase):
    """Tests for domain extraction."""
    
    def test_basic_domain(self):
        """Should extract basic domain."""
        self.assertEqual(
            get_domain("http://example.com/path"),
            "example.com"
        )
    
    def test_subdomain(self):
        """Should include subdomain."""
        self.assertEqual(
            get_domain("http://docs.example.com/path"),
            "docs.example.com"
        )
    
    def test_with_port(self):
        """Should include port in domain."""
        self.assertEqual(
            get_domain("http://example.com:8080/path"),
            "example.com:8080"
        )
    
    def test_lowercase(self):
        """Should lowercase domain."""
        self.assertEqual(
            get_domain("http://EXAMPLE.COM/path"),
            "example.com"
        )


class TestIsValidUrl(unittest.TestCase):
    """Tests for URL validation."""
    
    def test_valid_http(self):
        """Should accept http URLs."""
        self.assertTrue(is_valid_url("http://example.com"))
    
    def test_valid_https(self):
        """Should accept https URLs."""
        self.assertTrue(is_valid_url("https://example.com"))
    
    def test_invalid_scheme(self):
        """Should reject non-http(s) schemes."""
        self.assertFalse(is_valid_url("ftp://example.com"))
        self.assertFalse(is_valid_url("javascript:alert(1)"))
    
    def test_no_host(self):
        """Should reject URLs without host."""
        self.assertFalse(is_valid_url("http://"))
    
    def test_relative_url(self):
        """Should reject relative URLs."""
        self.assertFalse(is_valid_url("/path/to/page"))


if __name__ == '__main__':
    unittest.main()
