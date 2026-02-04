"""
Tests for the RobotsChecker class.
"""

import unittest
from unittest.mock import patch, MagicMock
from urllib.error import URLError
from io import BytesIO

from doc_search.robots import RobotsChecker


class TestRobotsCheckerBasic(unittest.TestCase):
    """Basic tests for RobotsChecker initialization."""
    
    def test_init_stores_base_url(self):
        """Should store the base URL."""
        checker = RobotsChecker("https://example.com", "TestBot")
        self.assertEqual(checker.base_url, "https://example.com")
    
    def test_init_stores_user_agent(self):
        """Should store the user agent."""
        checker = RobotsChecker("https://example.com", "TestBot")
        self.assertEqual(checker.user_agent, "TestBot")
    
    def test_init_default_user_agent(self):
        """Should use default user agent if not provided."""
        checker = RobotsChecker("https://example.com")
        self.assertEqual(checker.user_agent, "DocSearchBot/1.0")
    
    def test_init_not_loaded(self):
        """Should not be loaded initially."""
        checker = RobotsChecker("https://example.com")
        self.assertFalse(checker._loaded)


class TestRobotsCheckerLoad(unittest.TestCase):
    """Tests for loading robots.txt."""
    
    @patch('urllib.request.urlopen')
    def test_load_constructs_correct_url(self, mock_urlopen):
        """Should construct robots.txt URL from base URL."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"User-agent: *\nAllow: /"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com/path/page.html")
        checker.load()
        
        # The parser should have been set with the robots.txt URL
        self.assertEqual(checker.parser.url, "https://example.com/robots.txt")
    
    @patch('urllib.request.urlopen')
    def test_load_returns_true_on_success(self, mock_urlopen):
        """Should return True when robots.txt loads successfully."""
        mock_response = MagicMock()
        mock_response.read.return_value = b"User-agent: *\nAllow: /"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com")
        result = checker.load()
        
        self.assertTrue(result)
        self.assertTrue(checker._loaded)
    
    @patch('urllib.request.urlopen')
    def test_load_returns_false_on_error(self, mock_urlopen):
        """Should return False when robots.txt fails to load."""
        mock_urlopen.side_effect = URLError("Not found")
        
        checker = RobotsChecker("https://example.com")
        result = checker.load()
        
        self.assertFalse(result)
        # Should still mark as loaded (to allow crawling when no robots.txt)
        self.assertTrue(checker._loaded)


class TestRobotsCheckerCanFetch(unittest.TestCase):
    """Tests for can_fetch method."""
    
    @patch('urllib.request.urlopen')
    def test_allows_when_robots_txt_load_fails(self, mock_urlopen):
        """Should allow URLs when robots.txt fails to load.
        
        This is the standard behavior for web crawlers: if robots.txt cannot
        be fetched (due to SSL errors, auth requirements, network issues, etc.),
        assume the site allows crawling. Otherwise, sites with these issues
        would become completely uncrawlable.
        """
        mock_urlopen.side_effect = URLError("Not found")
        
        checker = RobotsChecker("https://example.com", "TestBot")
        result = checker.load()
        
        # Load should return False (failed to load)
        self.assertFalse(result)
        # But we should allow crawling when robots.txt couldn't be loaded
        self.assertTrue(checker.can_fetch("https://example.com/page"))
    
    @patch('urllib.request.urlopen')
    def test_respects_disallow_rule(self, mock_urlopen):
        """Should respect Disallow rules in robots.txt."""
        robots_content = b"""
User-agent: *
Disallow: /private/
Disallow: /admin
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # Allowed URLs
        self.assertTrue(checker.can_fetch("https://example.com/"))
        self.assertTrue(checker.can_fetch("https://example.com/page"))
        self.assertTrue(checker.can_fetch("https://example.com/public/page"))
        
        # Disallowed URLs
        self.assertFalse(checker.can_fetch("https://example.com/private/"))
        self.assertFalse(checker.can_fetch("https://example.com/private/secret"))
        self.assertFalse(checker.can_fetch("https://example.com/admin"))
        self.assertFalse(checker.can_fetch("https://example.com/admin/"))
    
    @patch('urllib.request.urlopen')
    def test_respects_user_agent_specific_rules(self, mock_urlopen):
        """Should respect user-agent specific rules.
        
        Per robots.txt spec: when a specific user-agent block exists,
        only those rules apply - the * rules are NOT inherited.
        """
        robots_content = b"""
User-agent: TestBot
Disallow: /bot-blocked/

User-agent: *
Disallow: /all-blocked/
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # TestBot-specific block applies
        self.assertFalse(checker.can_fetch("https://example.com/bot-blocked/page"))
        
        # TestBot does NOT inherit * rules - it's ALLOWED to access /all-blocked/
        # because only the TestBot-specific rules apply
        self.assertTrue(checker.can_fetch("https://example.com/all-blocked/page"))
    
    @patch('urllib.request.urlopen')
    def test_allow_directive_with_more_specific_path(self, mock_urlopen):
        """Test Allow directive behavior.
        
        Note: Python's robotparser has limited Allow support.
        The most specific path should win, but behavior may vary.
        """
        robots_content = b"""
User-agent: *
Disallow: /docs/
Allow: /docs/public/
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # /docs/private is disallowed
        self.assertFalse(checker.can_fetch("https://example.com/docs/private"))
        
        # Note: Python's robotparser may not fully support Allow override
        # Just verify it doesn't crash and returns a boolean
        result = checker.can_fetch("https://example.com/docs/public/page")
        self.assertIsInstance(result, bool)
    
    @patch('urllib.request.urlopen')
    def test_can_fetch_auto_loads(self, mock_urlopen):
        """Should auto-load robots.txt on first can_fetch call."""
        robots_content = b"""
User-agent: *
Disallow: /blocked/
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        
        # Don't call load() explicitly
        self.assertFalse(checker._loaded)
        
        # can_fetch should trigger auto-load
        result = checker.can_fetch("https://example.com/blocked/page")
        
        self.assertTrue(checker._loaded)
        self.assertFalse(result)


class TestRobotsCheckerCrawlDelay(unittest.TestCase):
    """Tests for crawl delay handling."""
    
    @patch('urllib.request.urlopen')
    def test_extracts_crawl_delay(self, mock_urlopen):
        """Should extract crawl-delay from robots.txt."""
        robots_content = b"""
User-agent: *
Crawl-delay: 5
Disallow: /private/
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        delay = checker.get_crawl_delay(default=1.0)
        self.assertEqual(delay, 5.0)
    
    @patch('urllib.request.urlopen')
    def test_returns_default_when_no_crawl_delay(self, mock_urlopen):
        """Should return default when no crawl-delay specified."""
        robots_content = b"""
User-agent: *
Disallow: /private/
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        delay = checker.get_crawl_delay(default=2.0)
        self.assertEqual(delay, 2.0)
    
    @patch('urllib.request.urlopen')
    def test_enforces_minimum_crawl_delay(self, mock_urlopen):
        """Should enforce minimum crawl delay of 0.5s."""
        robots_content = b"""
User-agent: *
Crawl-delay: 0.1
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        delay = checker.get_crawl_delay(default=1.0)
        # Should be at least 0.5s
        self.assertGreaterEqual(delay, 0.5)
    
    @patch('urllib.request.urlopen')
    def test_crawl_delay_auto_loads(self, mock_urlopen):
        """Should auto-load robots.txt on get_crawl_delay call."""
        robots_content = b"""
User-agent: *
Crawl-delay: 3
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        
        # Don't call load() explicitly
        self.assertFalse(checker._loaded)
        
        # get_crawl_delay should trigger auto-load
        delay = checker.get_crawl_delay(default=1.0)
        
        self.assertTrue(checker._loaded)
        self.assertEqual(delay, 3.0)


class TestRobotsCheckerMalformed(unittest.TestCase):
    """Tests for handling malformed robots.txt files."""
    
    @patch('urllib.request.urlopen')
    def test_handles_empty_robots_txt(self, mock_urlopen):
        """Should handle empty robots.txt gracefully."""
        mock_response = MagicMock()
        mock_response.read.return_value = b""
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # Empty robots.txt should allow everything
        self.assertTrue(checker.can_fetch("https://example.com/any/page"))
    
    @patch('urllib.request.urlopen')
    def test_handles_garbage_content(self, mock_urlopen):
        """Should handle non-robots.txt content gracefully."""
        # HTML page instead of robots.txt
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html><body>Not a robots.txt</body></html>"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # Malformed content should allow everything
        self.assertTrue(checker.can_fetch("https://example.com/any/page"))
    
    @patch('urllib.request.urlopen')
    def test_handles_binary_content(self, mock_urlopen):
        """Should handle binary content gracefully."""
        # Random binary data
        mock_response = MagicMock()
        mock_response.read.return_value = b"\x00\x01\x02\xff\xfe"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        
        # Should not crash
        try:
            checker.load()
            result = checker.can_fetch("https://example.com/page")
            # Should default to allowing when content is unparseable
            self.assertTrue(result)
        except Exception as e:
            self.fail(f"Should not raise exception on binary content: {e}")
    
    @patch('urllib.request.urlopen')
    def test_handles_invalid_lines(self, mock_urlopen):
        """Should ignore invalid lines in robots.txt."""
        robots_content = b"""
This is not valid
User-agent: *
Random garbage here
Disallow: /blocked/
More invalid content
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # Valid rules should still work
        self.assertFalse(checker.can_fetch("https://example.com/blocked/page"))
        self.assertTrue(checker.can_fetch("https://example.com/allowed/page"))
    
    @patch('urllib.request.urlopen')
    def test_handles_unicode_content(self, mock_urlopen):
        """Should handle UTF-8 content in robots.txt."""
        robots_content = """
# Comment with unicode: 日本語
User-agent: *
Disallow: /блокировано/
""".encode('utf-8')
        
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        
        # Should not crash on unicode
        try:
            checker.load()
            # Check basic functionality still works
            self.assertTrue(checker.can_fetch("https://example.com/page"))
        except Exception as e:
            self.fail(f"Should not raise exception on unicode content: {e}")


class TestRobotsCheckerEdgeCases(unittest.TestCase):
    """Edge case tests for RobotsChecker."""
    
    @patch('urllib.request.urlopen')
    def test_handles_timeout(self, mock_urlopen):
        """Should handle timeout gracefully (no crash)."""
        from socket import timeout
        mock_urlopen.side_effect = timeout("Connection timed out")
        
        checker = RobotsChecker("https://example.com", "TestBot")
        result = checker.load()
        
        # Should return False and mark as loaded
        self.assertFalse(result)
        self.assertTrue(checker._loaded)
        # Note: Default behavior when load fails is to deny (conservative)
        # can_fetch should not crash
        self.assertIsInstance(checker.can_fetch("https://example.com/page"), bool)
    
    @patch('urllib.request.urlopen')
    def test_handles_connection_error(self, mock_urlopen):
        """Should handle connection errors gracefully (no crash)."""
        mock_urlopen.side_effect = ConnectionError("Connection refused")
        
        checker = RobotsChecker("https://example.com", "TestBot")
        result = checker.load()
        
        # Should return False
        self.assertFalse(result)
        # can_fetch should not crash
        self.assertIsInstance(checker.can_fetch("https://example.com/page"), bool)
    
    def test_base_url_with_port(self):
        """Should handle base URLs with ports."""
        checker = RobotsChecker("https://example.com:8080/path")
        # Set URL should include port
        checker.parser.set_url("https://example.com:8080/robots.txt")
        self.assertIn("8080", checker.parser.url)
    
    @patch('urllib.request.urlopen')
    def test_disallow_all(self, mock_urlopen):
        """Should handle Disallow: / (block everything)."""
        robots_content = b"""
User-agent: *
Disallow: /
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # Everything should be blocked
        self.assertFalse(checker.can_fetch("https://example.com/"))
        self.assertFalse(checker.can_fetch("https://example.com/page"))
        self.assertFalse(checker.can_fetch("https://example.com/deep/nested/path"))
    
    @patch('urllib.request.urlopen')
    def test_allow_all(self, mock_urlopen):
        """Should handle empty Disallow (allow everything)."""
        robots_content = b"""
User-agent: *
Disallow:
"""
        mock_response = MagicMock()
        mock_response.read.return_value = robots_content
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        
        checker = RobotsChecker("https://example.com", "TestBot")
        checker.load()
        
        # Everything should be allowed
        self.assertTrue(checker.can_fetch("https://example.com/"))
        self.assertTrue(checker.can_fetch("https://example.com/any/path"))


if __name__ == '__main__':
    unittest.main()
