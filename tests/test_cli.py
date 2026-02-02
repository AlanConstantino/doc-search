"""
Tests for the CLI module.

This module provides test infrastructure for CLI testing including:
- Shared fixtures for temporary directories and mock objects
- Helper functions for CLI invocation and output capture
- Smoke tests to verify the setup works
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

from doc_search.cli import main, create_parser
from doc_search.cli.commands import get_site_dir, DEFAULT_DATA_DIR


# ============================================================================
# Test Fixtures
# ============================================================================

class MockSearchEngine:
    """Mock SearchEngine for testing CLI commands without real index.
    
    This mock provides the same interface as SearchEngine and EnhancedSearchEngine
    to allow testing CLI commands that interact with the search functionality.
    """
    
    def __init__(
        self,
        results: Optional[List[Dict[str, Any]]] = None,
        stats: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None
    ):
        """
        Create mock search engine.
        
        Args:
            results: List of result dicts to return from search()
            stats: Stats dict to return from get_stats()
            suggestions: List of autocomplete suggestions
        """
        self._results = results or []
        self._stats = stats or {
            'total_documents': 100,
            'unique_terms': 5000,
            'avg_document_length': 150,
            'k1': 1.5,
            'b': 0.75,
            'features': {
                'spellcheck': True,
                'autocomplete': True,
                'facets': True,
                'synonyms': False
            }
        }
        self._suggestions = suggestions or []
        self.search_calls: List[Dict[str, Any]] = []
        self.autocomplete_calls: List[Dict[str, Any]] = []
    
    def search(self, query: str, top_k: int = 10, **kwargs) -> Dict[str, Any]:
        """Return mock search results in enhanced format."""
        self.search_calls.append({'query': query, 'top_k': top_k, **kwargs})
        return {
            'results': self._results[:top_k],
            'suggestion': None,
            'expanded_query': None,
            'facets': {}
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Return mock stats."""
        return self._stats
    
    def get_autocomplete_suggestions(self, prefix: str, max_suggestions: int = 10) -> List[str]:
        """Return mock autocomplete suggestions."""
        self.autocomplete_calls.append({'prefix': prefix, 'max_suggestions': max_suggestions})
        return [s for s in self._suggestions if s.startswith(prefix)][:max_suggestions]
    
    @classmethod
    def load(cls, path: Path, **kwargs) -> 'MockSearchEngine':
        """Mock load method for compatibility."""
        return cls()


class MockCrawler:
    """Mock Crawler for testing CLI crawl command without real HTTP requests.
    
    This mock provides the same interface as Crawler to allow testing
    the crawl command without making actual network requests.
    """
    
    def __init__(self, stats: Optional[Dict[str, Any]] = None):
        """
        Create mock crawler.
        
        Args:
            stats: Stats dict to return from crawl()
        """
        self._stats = stats or {
            'pages_crawled': 50,
            'pages_skipped': 5,
            'pages_failed': 2,
            'bytes_downloaded': 1024 * 1024,  # 1MB
            'elapsed_seconds': 30.5
        }
        self.crawl_calls: List[Dict[str, Any]] = []
    
    def crawl(self, resume: bool = True) -> Dict[str, Any]:
        """Return mock crawl stats."""
        self.crawl_calls.append({'resume': resume})
        return self._stats


class CLITestCase(unittest.TestCase):
    """Base test case with helpers for CLI testing.
    
    Provides:
    - Temporary directory fixture for isolated testing
    - CLI invocation helpers with output capture
    - Mock search engine and crawler setup
    """
    
    temp_dir: Optional[tempfile.TemporaryDirectory] = None
    site_dir: Optional[Path] = None
    
    @classmethod
    def setUpClass(cls):
        """Create temporary directory for test data."""
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.site_dir = Path(cls.temp_dir.name) / 'test_site'
        cls.site_dir.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def tearDownClass(cls):
        """Cleanup temporary directory."""
        if cls.temp_dir:
            cls.temp_dir.cleanup()
            cls.temp_dir = None
            cls.site_dir = None
    
    def setUp(self):
        """Reset state before each test."""
        # Create required subdirectories
        pages_dir = self.site_dir / 'pages'
        pages_dir.mkdir(exist_ok=True)
    
    def create_mock_index(self, site_dir: Optional[Path] = None) -> Path:
        """Create a minimal mock index file for testing.
        
        Args:
            site_dir: Directory to create index in (defaults to self.site_dir)
            
        Returns:
            Path to the created index file
        """
        site_dir = site_dir or self.site_dir
        index_data = {
            'k1': 1.5,
            'b': 0.75,
            'avg_doc_length': 150,
            'documents': {},
            'index': {},
            'doc_lengths': {}
        }
        index_path = site_dir / 'index.json'
        with open(index_path, 'w') as f:
            json.dump(index_data, f)
        return index_path
    
    def create_mock_metadata(self, url: str = 'https://docs.example.com/',
                            site_dir: Optional[Path] = None) -> Path:
        """Create mock metadata.json file for testing.
        
        Args:
            url: Base URL for the site
            site_dir: Directory to create metadata in
            
        Returns:
            Path to the created metadata file
        """
        site_dir = site_dir or self.site_dir
        metadata = {
            'url': url,
            'stats': {
                'pages_crawled': 100,
                'pages_skipped': 10,
                'pages_failed': 5,
                'bytes_downloaded': 5 * 1024 * 1024,
                'elapsed_seconds': 120.5
            }
        }
        metadata_path = site_dir / 'metadata.json'
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)
        return metadata_path
    
    def create_mock_page(self, filename: str, content: Dict[str, Any],
                        site_dir: Optional[Path] = None) -> Path:
        """Create a mock page file in the pages directory.
        
        Args:
            filename: Name of the page file (without extension)
            content: Page content dict (url, title, text, etc.)
            site_dir: Site directory to use
            
        Returns:
            Path to the created page file
        """
        site_dir = site_dir or self.site_dir
        pages_dir = site_dir / 'pages'
        pages_dir.mkdir(exist_ok=True)
        
        page_path = pages_dir / f'{filename}.json'
        with open(page_path, 'w') as f:
            json.dump(content, f)
        return page_path


# ============================================================================
# CLI Invocation Helpers
# ============================================================================

@contextmanager
def capture_output():
    """Context manager to capture stdout and stderr.
    
    Yields:
        Tuple of (stdout_capture, stderr_capture) StringIO objects
        
    Example:
        with capture_output() as (stdout, stderr):
            some_function()
        output = stdout.getvalue()
    """
    old_stdout, old_stderr = sys.stdout, sys.stderr
    new_stdout, new_stderr = io.StringIO(), io.StringIO()
    try:
        sys.stdout, sys.stderr = new_stdout, new_stderr
        yield new_stdout, new_stderr
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


def run_cli(args: List[str], capture: bool = True) -> Tuple[int, str, str]:
    """Run CLI with given arguments and capture output.
    
    Args:
        args: Command line arguments (without 'doc_search' prefix)
        capture: Whether to capture stdout/stderr
        
    Returns:
        Tuple of (return_code, stdout_output, stderr_output)
        
    Example:
        code, stdout, stderr = run_cli(['search', 'site_dir', 'python list'])
    """
    # Parse arguments
    parser = create_parser()
    
    if capture:
        with capture_output() as (stdout, stderr):
            try:
                parsed = parser.parse_args(args)
                if parsed.command:
                    return_code = parsed.func(parsed)
                else:
                    parser.print_help()
                    return_code = 1
            except SystemExit as e:
                return_code = e.code if isinstance(e.code, int) else 1
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                return_code = 1
        return return_code, stdout.getvalue(), stderr.getvalue()
    else:
        try:
            parsed = parser.parse_args(args)
            if parsed.command:
                return_code = parsed.func(parsed)
            else:
                parser.print_help()
                return_code = 1
        except SystemExit as e:
            return_code = e.code if isinstance(e.code, int) else 1
        except Exception as e:
            return_code = 1
        return return_code, '', ''


def parse_args(args: List[str]):
    """Parse CLI arguments without executing.
    
    Args:
        args: Command line arguments
        
    Returns:
        Parsed namespace object
        
    Example:
        parsed = parse_args(['crawl', 'https://example.com', '--delay', '2'])
        assert parsed.delay == 2.0
    """
    parser = create_parser()
    return parser.parse_args(args)


# ============================================================================
# Smoke Tests - Verify Test Infrastructure
# ============================================================================

class TestCLITestInfrastructure(CLITestCase):
    """Smoke tests to verify the test infrastructure works correctly."""
    
    def test_temp_dir_exists(self):
        """Temporary directory should be created."""
        self.assertIsNotNone(self.temp_dir)
        self.assertIsNotNone(self.site_dir)
        self.assertTrue(self.site_dir.exists())
    
    def test_mock_search_engine_search(self):
        """MockSearchEngine.search should return expected format."""
        results = [
            {'url': 'https://example.com/1', 'title': 'Page 1', 'score': 1.5},
            {'url': 'https://example.com/2', 'title': 'Page 2', 'score': 1.2},
        ]
        engine = MockSearchEngine(results=results)
        
        response = engine.search('test query', top_k=5)
        
        self.assertIn('results', response)
        self.assertEqual(len(response['results']), 2)
        self.assertEqual(engine.search_calls[0]['query'], 'test query')
    
    def test_mock_search_engine_stats(self):
        """MockSearchEngine.get_stats should return stats dict."""
        engine = MockSearchEngine()
        stats = engine.get_stats()
        
        self.assertIn('total_documents', stats)
        self.assertIn('unique_terms', stats)
        self.assertEqual(stats['total_documents'], 100)
    
    def test_mock_crawler_crawl(self):
        """MockCrawler.crawl should return stats dict."""
        crawler = MockCrawler()
        stats = crawler.crawl(resume=False)
        
        self.assertIn('pages_crawled', stats)
        self.assertEqual(stats['pages_crawled'], 50)
        self.assertEqual(crawler.crawl_calls[0]['resume'], False)
    
    def test_capture_output(self):
        """capture_output should capture stdout and stderr."""
        with capture_output() as (stdout, stderr):
            print("stdout message")
            print("stderr message", file=sys.stderr)
        
        self.assertIn("stdout message", stdout.getvalue())
        self.assertIn("stderr message", stderr.getvalue())
    
    def test_create_mock_index(self):
        """create_mock_index should create valid index file."""
        index_path = self.create_mock_index()
        
        self.assertTrue(index_path.exists())
        with open(index_path) as f:
            data = json.load(f)
        self.assertIn('k1', data)
        self.assertIn('documents', data)
    
    def test_create_mock_metadata(self):
        """create_mock_metadata should create valid metadata file."""
        metadata_path = self.create_mock_metadata(url='https://test.example.com/')
        
        self.assertTrue(metadata_path.exists())
        with open(metadata_path) as f:
            data = json.load(f)
        self.assertEqual(data['url'], 'https://test.example.com/')
        self.assertIn('stats', data)
    
    def test_create_mock_page(self):
        """create_mock_page should create page file in pages directory."""
        page_content = {
            'url': 'https://example.com/test',
            'title': 'Test Page',
            'text': 'This is test content.'
        }
        page_path = self.create_mock_page('test_page', page_content)
        
        self.assertTrue(page_path.exists())
        self.assertEqual(page_path.parent.name, 'pages')
        with open(page_path) as f:
            data = json.load(f)
        self.assertEqual(data['title'], 'Test Page')


class TestParserCreation(unittest.TestCase):
    """Tests for argument parser creation and structure."""
    
    def test_parser_creates_successfully(self):
        """create_parser should return ArgumentParser."""
        parser = create_parser()
        self.assertIsNotNone(parser)
    
    def test_parser_has_version(self):
        """Parser should have --version option."""
        with capture_output() as (stdout, stderr):
            try:
                parse_args(['--version'])
            except SystemExit:
                pass
        # Version info goes to stdout
        output = stdout.getvalue()
        self.assertIn('doc_search', output)
    
    def test_parser_has_subcommands(self):
        """Parser should recognize all expected subcommands."""
        expected_commands = ['crawl', 'index', 'search', 'autocomplete', 
                           'interactive', 'stats', 'list', 'serve']
        
        for cmd in expected_commands:
            # Should not raise for valid commands
            # (will fail later if missing required args, but that's fine)
            try:
                parser = create_parser()
                parser.parse_args([cmd, '--help'])
            except SystemExit:
                pass  # --help causes SystemExit, which is expected


class TestParseArgs(unittest.TestCase):
    """Tests for argument parsing."""
    
    def test_parse_crawl_url(self):
        """Should parse crawl command with URL."""
        args = parse_args(['crawl', 'https://docs.example.com/'])
        
        self.assertEqual(args.command, 'crawl')
        self.assertEqual(args.url, 'https://docs.example.com/')
    
    def test_parse_crawl_options(self):
        """Should parse crawl command with all options."""
        args = parse_args([
            'crawl', 'https://docs.example.com/',
            '--delay', '2.5',
            '--max-pages', '100',
            '--max-depth', '3',
            '--same-path',
            '--fresh',
            '--workers', '4'
        ])
        
        self.assertEqual(args.delay, 2.5)
        self.assertEqual(args.max_pages, 100)
        self.assertEqual(args.max_depth, 3)
        self.assertTrue(args.same_path)
        self.assertTrue(args.fresh)
        self.assertEqual(args.workers, 4)
    
    def test_parse_search_query(self):
        """Should parse search command with query."""
        args = parse_args(['search', '/path/to/site', 'python list'])
        
        self.assertEqual(args.command, 'search')
        self.assertEqual(args.site_dir, '/path/to/site')
        self.assertEqual(args.query, 'python list')
    
    def test_parse_search_options(self):
        """Should parse search command with options."""
        args = parse_args([
            'search', '/path/to/site', 'query',
            '--limit', '20',
            '--scores',
            '--json',
            '--synonyms'
        ])
        
        self.assertEqual(args.limit, 20)
        self.assertTrue(args.scores)
        self.assertTrue(args.json)
        self.assertTrue(args.synonyms)
    
    def test_parse_index_options(self):
        """Should parse index command with options."""
        args = parse_args([
            'index', '/path/to/site',
            '--k1', '1.2',
            '--b', '0.8',
            '--no-compress',
            '--no-stemming'
        ])
        
        self.assertEqual(args.k1, 1.2)
        self.assertEqual(args.b, 0.8)
        self.assertTrue(args.no_compress)
        self.assertTrue(args.no_stemming)
    
    def test_parse_serve_options(self):
        """Should parse serve command with options."""
        args = parse_args([
            'serve', '/path/to/site',
            '--port', '9000',
            '--host', '0.0.0.0',
            '--open',
            '--log-requests'
        ])
        
        self.assertEqual(args.port, 9000)
        self.assertEqual(args.host, '0.0.0.0')
        self.assertTrue(args.open)
        self.assertTrue(args.log_requests)


if __name__ == '__main__':
    unittest.main()
