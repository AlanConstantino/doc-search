"""
Tests for utility functions including URL normalization.
"""

import base64
import ssl
import unittest
from doc_search.utils import (
    normalize_url, tokenize, tokenize_phrase, is_valid_url, get_domain,
    hash_string, url_to_filename, site_hash, make_basic_auth_header,
    create_permissive_ssl_context
)


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

    def test_tokenize_phrase_keeps_stopwords_and_surface_form(self):
        """Quoted/exact phrases keep glue words and do not stem or split."""
        self.assertEqual(tokenize_phrase("list of lists"), ["list", "of", "lists"])
        self.assertEqual(tokenize_phrase("running files"), ["running", "files"])
        self.assertEqual(tokenize_phrase("HTTPResponse"), ["httpresponse"])
    
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


    def test_keeps_programming_keywords(self):
        """Docs/search keywords must not be stripped as stopwords."""
        cases = {
            'async with': ['async', 'with'],
            'yield from': ['yield', 'from'],
            'for loop': ['for', 'loop'],
            'with open': ['with', 'open'],
            'not implemented': ['not', 'implemented'],
            'if else': ['if', 'else'],
        }
        for query, expected in cases.items():
            tokens = tokenize(query)
            for term in expected:
                self.assertIn(term, tokens, msg=f'{query!r} missing {term!r}: {tokens}')

    def test_keeps_numeric_tokens(self):
        """Should keep pure numeric tokens for number search."""
        tokens = tokenize("Version 2024 and 7")
        self.assertIn("2024", tokens)
        self.assertIn("7", tokens)

    def test_splits_glued_alphanumerics(self):
        """ticket1234 should be searchable as 1234 and as ticket1234."""
        tokens = tokenize("ticket1234")
        self.assertIn("1234", tokens)
        self.assertIn("ticket", tokens)
        self.assertIn("ticket1234", tokens)

    def test_digit_leading_tokens(self):
        """Tokens that start with a digit must stay searchable."""
        cases = {
            "3d": ["3d", "3"],
            "7zip": ["7zip", "7", "zip"],
            "64bit": ["64bit", "64", "bit"],
            "404page": ["404page", "404", "page"],
        }
        for query, expected in cases.items():
            tokens = tokenize(query)
            for term in expected:
                self.assertIn(term, tokens, msg=f"{query!r} missing {term!r}: {tokens}")

    def test_versions_and_hex(self):
        """Versions, thousands separators, and hex should be kept as tokens."""
        self.assertIn("3.12", tokenize("Python 3.12"))
        self.assertIn("2.6.3", tokenize("v2.6.3"))
        self.assertIn("12345", tokenize("12,345"))
        self.assertIn("0x1234", tokenize("mask 0x1234"))
        self.assertIn("1234", tokenize("mask 0x1234"))

    def test_number_query_repeats_keep_tf(self):
        """Repeated numbers must not be collapsed (BM25 tf)."""
        tokens = tokenize("ticket 1234 ticket 1234")
        self.assertEqual(tokens.count("1234"), 2)
        self.assertEqual(tokens.count("ticket"), 2)


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


class TestHashString(unittest.TestCase):
    """Tests for hash_string function."""
    
    def test_default_length(self):
        """Default length should be 16 characters."""
        result = hash_string("test")
        self.assertEqual(len(result), 16)
    
    def test_custom_length(self):
        """Should respect custom length parameter."""
        result = hash_string("test", length=8)
        self.assertEqual(len(result), 8)
        
        result = hash_string("test", length=32)
        self.assertEqual(len(result), 32)
    
    def test_deterministic(self):
        """Same input should produce same output."""
        result1 = hash_string("hello world")
        result2 = hash_string("hello world")
        self.assertEqual(result1, result2)
    
    def test_different_inputs(self):
        """Different inputs should produce different outputs."""
        result1 = hash_string("test1")
        result2 = hash_string("test2")
        self.assertNotEqual(result1, result2)
    
    def test_hex_characters(self):
        """Output should be valid hex characters."""
        import re
        result = hash_string("test")
        self.assertTrue(re.match(r'^[0-9a-f]+$', result))


class TestUrlToFilename(unittest.TestCase):
    """Tests for url_to_filename function."""
    
    def test_returns_hash(self):
        """Should return a hash string."""
        result = url_to_filename("https://example.com/page")
        self.assertEqual(len(result), 16)
    
    def test_deterministic(self):
        """Same URL should produce same filename."""
        url = "https://example.com/test"
        result1 = url_to_filename(url)
        result2 = url_to_filename(url)
        self.assertEqual(result1, result2)
    
    def test_different_urls(self):
        """Different URLs should produce different filenames."""
        result1 = url_to_filename("https://example.com/page1")
        result2 = url_to_filename("https://example.com/page2")
        self.assertNotEqual(result1, result2)


class TestSiteHash(unittest.TestCase):
    """Tests for site_hash function."""
    
    def test_default_length(self):
        """Should return 12-character hash by default."""
        result = site_hash("https://example.com/docs")
        self.assertEqual(len(result), 12)
    
    def test_domain_only_default(self):
        """By default, should hash only the domain."""
        result1 = site_hash("https://example.com/path1")
        result2 = site_hash("https://example.com/path2")
        self.assertEqual(result1, result2)
    
    def test_include_path(self):
        """With include_path=True, should include path in hash."""
        result1 = site_hash("https://example.com/path1", include_path=True)
        result2 = site_hash("https://example.com/path2", include_path=True)
        self.assertNotEqual(result1, result2)
    
    def test_trailing_slash_normalized(self):
        """Trailing slash should not affect hash when include_path=True."""
        result1 = site_hash("https://example.com/docs/", include_path=True)
        result2 = site_hash("https://example.com/docs", include_path=True)
        self.assertEqual(result1, result2)


class TestMakeBasicAuthHeader(unittest.TestCase):
    """Tests for make_basic_auth_header function."""
    
    def test_no_credentials(self):
        """Should return None when no credentials provided."""
        result = make_basic_auth_header()
        self.assertIsNone(result)
    
    def test_username_password(self):
        """Should encode username:password as Base64."""
        result = make_basic_auth_header(auth=("user", "pass"))
        # "user:pass" -> base64 -> "dXNlcjpwYXNz"
        expected = "Basic dXNlcjpwYXNz"
        self.assertEqual(result, expected)
    
    def test_username_password_special_chars(self):
        """Should handle special characters in credentials."""
        result = make_basic_auth_header(auth=("user@domain.com", "p@ss:word!"))
        # Verify it's a valid Base64 encoding
        self.assertTrue(result.startswith("Basic "))
        # Decode and verify
        token = result[6:]  # Remove "Basic "
        decoded = base64.b64decode(token).decode()
        self.assertEqual(decoded, "user@domain.com:p@ss:word!")
    
    def test_pre_encoded_token(self):
        """Should use pre-encoded token directly."""
        token = base64.b64encode(b"user:pass").decode()
        result = make_basic_auth_header(auth_token=token)
        self.assertEqual(result, f"Basic {token}")
    
    def test_pre_encoded_token_with_basic_prefix(self):
        """Should strip 'Basic ' prefix if included in token."""
        token = base64.b64encode(b"user:pass").decode()
        result = make_basic_auth_header(auth_token=f"Basic {token}")
        self.assertEqual(result, f"Basic {token}")
    
    def test_pre_encoded_token_with_lowercase_prefix(self):
        """Should strip 'basic ' prefix (case-insensitive)."""
        token = base64.b64encode(b"user:pass").decode()
        result = make_basic_auth_header(auth_token=f"basic {token}")
        self.assertEqual(result, f"Basic {token}")
    
    def test_token_takes_priority(self):
        """Token should take priority over username/password."""
        token = base64.b64encode(b"token:creds").decode()
        result = make_basic_auth_header(
            auth=("user", "pass"),
            auth_token=token
        )
        # Should use token, not auth
        self.assertEqual(result, f"Basic {token}")
        # Verify it's NOT the auth credentials
        decoded = base64.b64decode(token).decode()
        self.assertEqual(decoded, "token:creds")
    
    def test_empty_password(self):
        """Should handle empty password."""
        result = make_basic_auth_header(auth=("user", ""))
        self.assertTrue(result.startswith("Basic "))
        token = result[6:]
        decoded = base64.b64decode(token).decode()
        self.assertEqual(decoded, "user:")
    
    def test_empty_username(self):
        """Should handle empty username."""
        result = make_basic_auth_header(auth=("", "pass"))
        self.assertTrue(result.startswith("Basic "))
        token = result[6:]
        decoded = base64.b64decode(token).decode()
        self.assertEqual(decoded, ":pass")


class TestCreatePermissiveSslContext(unittest.TestCase):
    """Tests for create_permissive_ssl_context function."""
    
    def test_returns_ssl_context(self):
        """Should return an SSLContext instance."""
        ctx = create_permissive_ssl_context()
        self.assertIsInstance(ctx, ssl.SSLContext)
    
    def test_check_hostname_disabled(self):
        """Should have hostname checking disabled."""
        ctx = create_permissive_ssl_context()
        self.assertFalse(ctx.check_hostname)
    
    def test_cert_verification_disabled(self):
        """Should have certificate verification disabled (CERT_NONE)."""
        ctx = create_permissive_ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
    
    def test_returns_new_instance_each_call(self):
        """Should return a new SSLContext on each call."""
        ctx1 = create_permissive_ssl_context()
        ctx2 = create_permissive_ssl_context()
        self.assertIsNot(ctx1, ctx2)


if __name__ == '__main__':
    unittest.main()
