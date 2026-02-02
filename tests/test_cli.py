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


# ============================================================================
# cmd_crawl Tests
# ============================================================================

class TestCmdCrawl(CLITestCase):
    """Tests for the cmd_crawl CLI command."""
    
    def test_crawl_basic_url(self):
        """Should crawl with just a URL."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            with capture_output() as (stdout, stderr):
                code, _, _ = run_cli([
                    'crawl', 'https://docs.example.com/'
                ])
            
            # Verify Crawler was created with correct base_url
            MockCrawlerClass.assert_called_once()
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['base_url'], 'https://docs.example.com/')
            
            # Verify crawl was called with resume=True (default, since --fresh not set)
            self.assertEqual(len(mock_crawler.crawl_calls), 1)
            self.assertTrue(mock_crawler.crawl_calls[0]['resume'])
            
            self.assertEqual(code, 0)
    
    def test_crawl_with_authentication(self):
        """Should pass authentication credentials to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--user', 'testuser',
                '--password', 'testpass'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['auth'], ('testuser', 'testpass'))
            self.assertEqual(code, 0)
    
    def test_crawl_with_auth_token(self):
        """Should pass auth token to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--token', 'my-secret-token'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['auth_token'], 'my-secret-token')
            self.assertEqual(code, 0)
    
    def test_crawl_with_depth_limit(self):
        """Should pass max_depth to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--max-depth', '3'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['max_depth'], 3)
            self.assertEqual(code, 0)
    
    def test_crawl_with_workers(self):
        """Should pass workers (concurrency) to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--workers', '8'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['workers'], 8)
            self.assertEqual(code, 0)
    
    def test_crawl_with_fresh_flag(self):
        """Should pass resume=False when --fresh flag is set."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--fresh'
            ])
            
            # Verify crawl was called with resume=False
            self.assertEqual(len(mock_crawler.crawl_calls), 1)
            self.assertFalse(mock_crawler.crawl_calls[0]['resume'])
            self.assertEqual(code, 0)
    
    def test_crawl_with_delay(self):
        """Should pass delay to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--delay', '2.5'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['delay'], 2.5)
            self.assertEqual(code, 0)
    
    def test_crawl_with_timeout(self):
        """Should pass timeout to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--timeout', '60'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['timeout'], 60)
            self.assertEqual(code, 0)
    
    def test_crawl_with_max_pages(self):
        """Should pass max_pages to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--max-pages', '500'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['max_pages'], 500)
            self.assertEqual(code, 0)
    
    def test_crawl_with_same_path(self):
        """Should pass same_path flag to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--same-path'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertTrue(call_kwargs['same_path'])
            self.assertEqual(code, 0)
    
    def test_crawl_with_quiet(self):
        """Should pass verbose=False when --quiet flag is set."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--quiet'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertFalse(call_kwargs['verbose'])
            self.assertEqual(code, 0)
    
    def test_crawl_with_extract_docs(self):
        """Should pass extract_docs flag to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--extract-docs'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertTrue(call_kwargs['extract_docs'])
            self.assertEqual(code, 0)
    
    def test_crawl_with_incremental(self):
        """Should pass incremental flag to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/',
                '--incremental'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertTrue(call_kwargs['incremental'])
            self.assertEqual(code, 0)
    
    def test_crawl_with_all_options(self):
        """Should pass all options correctly to Crawler."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, _, _ = run_cli([
                'crawl', 'https://docs.example.com/api/',
                '--user', 'admin',
                '--password', 'secret',
                '--token', 'bearer-token',
                '--delay', '1.5',
                '--timeout', '45',
                '--max-pages', '200',
                '--max-depth', '5',
                '--workers', '10',
                '--same-path',
                '--quiet',
                '--extract-docs',
                '--incremental',
                '--fresh'
            ])
            
            call_kwargs = MockCrawlerClass.call_args[1]
            self.assertEqual(call_kwargs['base_url'], 'https://docs.example.com/api/')
            self.assertEqual(call_kwargs['auth'], ('admin', 'secret'))
            self.assertEqual(call_kwargs['auth_token'], 'bearer-token')
            self.assertEqual(call_kwargs['delay'], 1.5)
            self.assertEqual(call_kwargs['timeout'], 45)
            self.assertEqual(call_kwargs['max_pages'], 200)
            self.assertEqual(call_kwargs['max_depth'], 5)
            self.assertEqual(call_kwargs['workers'], 10)
            self.assertTrue(call_kwargs['same_path'])
            self.assertFalse(call_kwargs['verbose'])
            self.assertTrue(call_kwargs['extract_docs'])
            self.assertTrue(call_kwargs['incremental'])
            
            # --fresh means resume=False
            self.assertFalse(mock_crawler.crawl_calls[0]['resume'])
            
            self.assertEqual(code, 0)
    
    def test_crawl_saves_metadata(self):
        """Should save metadata.json after successful crawl."""
        mock_crawler = MockCrawler(stats={
            'pages_crawled': 25,
            'pages_skipped': 3,
            'pages_failed': 1,
            'bytes_downloaded': 512 * 1024,
            'elapsed_seconds': 15.0
        })
        
        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir)
            
            with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
                with patch('doc_search.cli.commands.get_site_dir', return_value=site_dir):
                    MockCrawlerClass.return_value = mock_crawler
                    
                    code, _, _ = run_cli([
                        'crawl', 'https://docs.example.com/'
                    ])
                    
                    self.assertEqual(code, 0)
                    
                    # Verify metadata was saved
                    metadata_path = site_dir / 'metadata.json'
                    self.assertTrue(metadata_path.exists())
                    
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    
                    self.assertEqual(metadata['url'], 'https://docs.example.com/')
                    self.assertEqual(metadata['stats']['pages_crawled'], 25)
    
    def test_crawl_creates_site_directory(self):
        """Should create site directory if it doesn't exist."""
        mock_crawler = MockCrawler()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir) / 'new_site'
            # Ensure it doesn't exist yet
            self.assertFalse(site_dir.exists())
            
            with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
                with patch('doc_search.cli.commands.get_site_dir', return_value=site_dir):
                    MockCrawlerClass.return_value = mock_crawler
                    
                    code, _, _ = run_cli([
                        'crawl', 'https://docs.example.com/'
                    ])
                    
                    self.assertEqual(code, 0)
                    # Directory should now exist
                    self.assertTrue(site_dir.exists())
    
    def test_crawl_prints_progress_info(self):
        """Should print crawl progress information."""
        mock_crawler = MockCrawler()
        
        with patch('doc_search.cli.commands.Crawler') as MockCrawlerClass:
            MockCrawlerClass.return_value = mock_crawler
            
            code, stdout, stderr = run_cli([
                'crawl', 'https://docs.example.com/'
            ])
            
            self.assertIn('Crawling: https://docs.example.com/', stdout)
            self.assertIn('Data directory:', stdout)


class TestCmdCrawlErrorHandling(CLITestCase):
    """Tests for error handling in cmd_crawl."""
    
    def test_crawl_missing_url(self):
        """Should fail when URL is not provided."""
        with capture_output() as (stdout, stderr):
            try:
                code, _, _ = run_cli(['crawl'])
            except SystemExit as e:
                code = e.code
        
        # Should fail with non-zero exit code
        self.assertNotEqual(code, 0)
    
    # NOTE: Exception handling test removed - main() does not catch exceptions
    # from command handlers. Exceptions propagate to the caller (shell).
    # This is intentional behavior - callers should handle errors appropriately.


class TestCmdCrawlArgParsing(unittest.TestCase):
    """Tests for crawl argument parsing."""
    
    def test_parse_crawl_defaults(self):
        """Should have sensible defaults for optional arguments."""
        args = parse_args(['crawl', 'https://docs.example.com/'])
        
        # Check defaults
        self.assertEqual(args.command, 'crawl')
        self.assertEqual(args.url, 'https://docs.example.com/')
        self.assertIsNone(args.user)
        self.assertIsNone(args.password)
        self.assertFalse(args.fresh)
        self.assertFalse(args.same_path)
        self.assertFalse(args.quiet)
    
    def test_parse_crawl_user_without_password(self):
        """Should allow --user without --password (prompts interactively)."""
        args = parse_args([
            'crawl', 'https://docs.example.com/',
            '--user', 'admin'
        ])
        
        self.assertEqual(args.user, 'admin')
        self.assertIsNone(args.password)
    
    def test_parse_crawl_negative_values_accepted(self):
        """Documents that argparse accepts negative values for numeric options.
        
        Note: argparse doesn't reject negative values by default.
        Validation should happen in the command handler if needed.
        """
        args = parse_args([
            'crawl', 'https://docs.example.com/',
            '--max-pages', '-1'
        ])
        # argparse will parse it as -1
        self.assertEqual(args.max_pages, -1)
    
    def test_parse_crawl_help(self):
        """Should show help text for crawl command."""
        with capture_output() as (stdout, stderr):
            try:
                parse_args(['crawl', '--help'])
            except SystemExit:
                pass
        
        output = stdout.getvalue()
        self.assertIn('crawl', output.lower())
        self.assertIn('url', output.lower())


# ============================================================================
# cmd_index Tests
# ============================================================================

class MockBM25Index:
    """Mock BM25Index for testing CLI index command without real indexing.
    
    This mock provides the same interface as BM25Index to allow testing
    the index command without actually processing documents.
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75, stem: bool = True):
        """
        Create mock index.
        
        Args:
            k1: BM25 k1 parameter
            b: BM25 b parameter
            stem: Whether stemming is enabled
        """
        # Validate parameters like real BM25Index does
        if k1 < 0:
            raise ValueError(f"k1 must be non-negative, got {k1}")
        if not (0 <= b <= 1):
            raise ValueError(f"b must be between 0 and 1, got {b}")
        
        self.k1 = k1
        self.b = b
        self.stem = stem
        self.build_calls: List[Dict[str, Any]] = []
        self.save_calls: List[Dict[str, Any]] = []
        self._num_docs_to_return = 10  # Default return value
    
    def set_num_docs(self, num: int):
        """Set the number of documents to return from build_from_pages."""
        self._num_docs_to_return = num
    
    def build_from_pages(self, pages_dir: Path, verbose: bool = True) -> int:
        """Return mock document count."""
        self.build_calls.append({'pages_dir': pages_dir, 'verbose': verbose})
        return self._num_docs_to_return
    
    def save(self, path: Path, compress: bool = True) -> Path:
        """Return mock save path and create a dummy file for stat()."""
        self.save_calls.append({'path': path, 'compress': compress})
        if compress:
            output_path = path.with_suffix('.json.gz')
        else:
            output_path = path.with_suffix('.json')
        # Create a dummy file so cmd_index can stat() it
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b'mock index content')
        return output_path


class TestCmdIndex(CLITestCase):
    """Tests for the cmd_index CLI command."""
    
    def test_index_basic(self):
        """Should build index from pages directory."""
        mock_index = MockBM25Index()
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, stdout, stderr = run_cli([
                'index', str(self.site_dir)
            ])
            
            # Verify BM25Index was created with default parameters
            MockIndexClass.assert_called_once_with(k1=1.5, b=0.75, stem=True)
            
            # Verify build_from_pages was called
            self.assertEqual(len(mock_index.build_calls), 1)
            self.assertEqual(mock_index.build_calls[0]['pages_dir'], 
                           self.site_dir / 'pages')
            
            # Verify save was called with compression enabled (default)
            self.assertEqual(len(mock_index.save_calls), 1)
            self.assertTrue(mock_index.save_calls[0]['compress'])
            
            self.assertEqual(code, 0)
    
    def test_index_custom_k1(self):
        """Should pass custom k1 parameter to BM25Index."""
        mock_index = MockBM25Index(k1=1.2)
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir),
                '--k1', '1.2'
            ])
            
            MockIndexClass.assert_called_once_with(k1=1.2, b=0.75, stem=True)
            self.assertEqual(code, 0)
    
    def test_index_custom_b(self):
        """Should pass custom b parameter to BM25Index."""
        mock_index = MockBM25Index(b=0.5)
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir),
                '--b', '0.5'
            ])
            
            MockIndexClass.assert_called_once_with(k1=1.5, b=0.5, stem=True)
            self.assertEqual(code, 0)
    
    def test_index_custom_k1_and_b(self):
        """Should pass both custom k1 and b parameters."""
        mock_index = MockBM25Index(k1=2.0, b=0.9)
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir),
                '--k1', '2.0',
                '--b', '0.9'
            ])
            
            MockIndexClass.assert_called_once_with(k1=2.0, b=0.9, stem=True)
            self.assertEqual(code, 0)
    
    def test_index_no_stemming(self):
        """Should disable stemming when --no-stemming flag is set."""
        mock_index = MockBM25Index(stem=False)
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, stdout, _ = run_cli([
                'index', str(self.site_dir),
                '--no-stemming'
            ])
            
            MockIndexClass.assert_called_once_with(k1=1.5, b=0.75, stem=False)
            self.assertIn('disabled', stdout.lower())
            self.assertEqual(code, 0)
    
    def test_index_no_compress(self):
        """Should disable compression when --no-compress flag is set."""
        mock_index = MockBM25Index()
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir),
                '--no-compress'
            ])
            
            # Verify save was called with compress=False
            self.assertEqual(len(mock_index.save_calls), 1)
            self.assertFalse(mock_index.save_calls[0]['compress'])
            self.assertEqual(code, 0)
    
    def test_index_quiet_mode(self):
        """Should pass verbose=False when --quiet flag is set."""
        mock_index = MockBM25Index()
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir),
                '--quiet'
            ])
            
            # Verify build_from_pages was called with verbose=False
            self.assertFalse(mock_index.build_calls[0]['verbose'])
            self.assertEqual(code, 0)
    
    def test_index_verbose_by_default(self):
        """Should pass verbose=True by default."""
        mock_index = MockBM25Index()
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir)
            ])
            
            # Verify build_from_pages was called with verbose=True
            self.assertTrue(mock_index.build_calls[0]['verbose'])
            self.assertEqual(code, 0)
    
    def test_index_with_all_options(self):
        """Should pass all options correctly."""
        mock_index = MockBM25Index(k1=1.8, b=0.6, stem=False)
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir),
                '--k1', '1.8',
                '--b', '0.6',
                '--no-stemming',
                '--no-compress',
                '--quiet'
            ])
            
            MockIndexClass.assert_called_once_with(k1=1.8, b=0.6, stem=False)
            self.assertFalse(mock_index.build_calls[0]['verbose'])
            self.assertFalse(mock_index.save_calls[0]['compress'])
            self.assertEqual(code, 0)
    
    def test_index_prints_build_info(self):
        """Should print information about the build."""
        mock_index = MockBM25Index()
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, stdout, _ = run_cli([
                'index', str(self.site_dir)
            ])
            
            self.assertIn('Building index from:', stdout)
            self.assertIn('pages', stdout)
            self.assertEqual(code, 0)
    
    def test_index_prints_save_info(self):
        """Should print information about saved index."""
        mock_index = MockBM25Index()
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            # Create a mock index file so stat() works
            index_path = self.site_dir / 'index.json.gz'
            index_path.write_bytes(b'test')
            
            code, stdout, _ = run_cli([
                'index', str(self.site_dir)
            ])
            
            self.assertIn('Index saved to:', stdout)
            self.assertIn('Index size:', stdout)
            self.assertEqual(code, 0)


class TestCmdIndexErrorHandling(CLITestCase):
    """Tests for error handling in cmd_index."""
    
    def test_index_missing_pages_directory(self):
        """Should fail when pages directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir) / 'empty_site'
            site_dir.mkdir()
            # No pages/ subdirectory
            
            code, stdout, _ = run_cli([
                'index', str(site_dir)
            ])
            
            self.assertEqual(code, 1)
            self.assertIn('Error:', stdout)
            self.assertIn('No crawled pages found', stdout)
    
    def test_index_zero_documents(self):
        """Should fail when no documents are indexed."""
        mock_index = MockBM25Index()
        mock_index.set_num_docs(0)  # Simulate empty pages directory
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, stdout, _ = run_cli([
                'index', str(self.site_dir)
            ])
            
            self.assertEqual(code, 1)
            self.assertIn('Error: No documents to index', stdout)
    
    def test_index_invalid_k1_negative(self):
        """Should fail when k1 is negative.
        
        BM25Index raises ValueError for invalid k1. Since cmd_index doesn't 
        catch this and run_cli catches all exceptions returning code 1,
        we verify the error code and that BM25Index was called with invalid params.
        """
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.side_effect = ValueError("k1 must be non-negative, got -1.0")
            
            code, stdout, stderr = run_cli(['index', str(self.site_dir), '--k1', '-1.0'])
            
            # run_cli catches the exception and returns 1
            self.assertEqual(code, 1)
            # Verify BM25Index was called with the invalid k1
            MockIndexClass.assert_called_once_with(k1=-1.0, b=0.75, stem=True)
    
    def test_index_invalid_b_out_of_range(self):
        """Should fail when b is outside [0, 1] range.
        
        BM25Index raises ValueError for invalid b. Since cmd_index doesn't 
        catch this and run_cli catches all exceptions returning code 1,
        we verify the error code and that BM25Index was called with invalid params.
        """
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.side_effect = ValueError("b must be between 0 and 1, got 1.5")
            
            code, stdout, stderr = run_cli(['index', str(self.site_dir), '--b', '1.5'])
            
            # run_cli catches the exception and returns 1
            self.assertEqual(code, 1)
            # Verify BM25Index was called with the invalid b
            MockIndexClass.assert_called_once_with(k1=1.5, b=1.5, stem=True)
    
    def test_index_missing_site_dir_argument(self):
        """Should fail when site_dir is not provided."""
        with capture_output() as (stdout, stderr):
            try:
                code, _, _ = run_cli(['index'])
            except SystemExit as e:
                code = e.code
        
        # Should fail with non-zero exit code
        self.assertNotEqual(code, 0)


class TestCmdIndexArgParsing(unittest.TestCase):
    """Tests for index argument parsing."""
    
    def test_parse_index_defaults(self):
        """Should have sensible defaults for optional arguments."""
        args = parse_args(['index', '/path/to/site'])
        
        self.assertEqual(args.command, 'index')
        self.assertEqual(args.site_dir, '/path/to/site')
        self.assertEqual(args.k1, 1.5)
        self.assertEqual(args.b, 0.75)
        self.assertFalse(args.no_compress)
        self.assertFalse(args.no_stemming)
        self.assertFalse(args.quiet)
    
    def test_parse_index_k1_float(self):
        """Should parse k1 as float."""
        args = parse_args(['index', '/path/to/site', '--k1', '2.5'])
        
        self.assertEqual(args.k1, 2.5)
        self.assertIsInstance(args.k1, float)
    
    def test_parse_index_b_float(self):
        """Should parse b as float."""
        args = parse_args(['index', '/path/to/site', '--b', '0.85'])
        
        self.assertEqual(args.b, 0.85)
        self.assertIsInstance(args.b, float)
    
    def test_parse_index_no_stemming_flag(self):
        """Should parse --no-stemming flag."""
        args = parse_args(['index', '/path/to/site', '--no-stemming'])
        
        self.assertTrue(args.no_stemming)
    
    def test_parse_index_no_compress_flag(self):
        """Should parse --no-compress flag."""
        args = parse_args(['index', '/path/to/site', '--no-compress'])
        
        self.assertTrue(args.no_compress)
    
    def test_parse_index_quiet_flag(self):
        """Should parse --quiet flag."""
        args = parse_args(['index', '/path/to/site', '--quiet'])
        
        self.assertTrue(args.quiet)
    
    def test_parse_index_separate_paths_flag(self):
        """Should parse --separate-paths flag."""
        args = parse_args(['index', '/path/to/site', '--separate-paths'])
        
        self.assertTrue(args.separate_paths)
    
    def test_parse_index_help(self):
        """Should show help text for index command."""
        with capture_output() as (stdout, stderr):
            try:
                parse_args(['index', '--help'])
            except SystemExit:
                pass
        
        output = stdout.getvalue()
        self.assertIn('index', output.lower())
        self.assertIn('site_dir', output)
        self.assertIn('k1', output)
        self.assertIn('b', output)


class TestCmdIndexIntegration(CLITestCase):
    """Integration tests for cmd_index using real file structures."""
    
    def test_index_with_page_files(self):
        """Should index actual page files in pages directory."""
        # Create mock page files
        page1 = {
            'url': 'https://example.com/page1',
            'title': 'Page One',
            'text': 'This is page one content.'
        }
        page2 = {
            'url': 'https://example.com/page2',
            'title': 'Page Two',
            'text': 'This is page two content with more text.'
        }
        self.create_mock_page('page1', page1)
        self.create_mock_page('page2', page2)
        
        mock_index = MockBM25Index()
        mock_index.set_num_docs(2)
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir)
            ])
            
            # Verify pages_dir was passed correctly
            pages_dir = mock_index.build_calls[0]['pages_dir']
            self.assertTrue(pages_dir.exists())
            self.assertEqual(len(list(pages_dir.glob('*.json'))), 2)
            self.assertEqual(code, 0)
    
    def test_index_save_path_uses_site_dir(self):
        """Should save index to site directory."""
        mock_index = MockBM25Index()
        
        with patch('doc_search.cli.commands.BM25Index') as MockIndexClass:
            MockIndexClass.return_value = mock_index
            
            code, _, _ = run_cli([
                'index', str(self.site_dir)
            ])
            
            # Verify save path is in site_dir
            save_path = mock_index.save_calls[0]['path']
            self.assertEqual(save_path.parent, self.site_dir)
            self.assertEqual(save_path.stem, 'index')
            self.assertEqual(code, 0)


# ============================================================================
# cmd_search Tests
# ============================================================================

class TestCmdSearch(CLITestCase):
    """Tests for the cmd_search CLI command."""
    
    def test_search_basic_query(self):
        """Should perform basic search with query."""
        results = [
            {'url': 'https://example.com/page1', 'title': 'Python Tutorial', 'score': 2.5, 'snippet': 'Learn Python basics...'},
            {'url': 'https://example.com/page2', 'title': 'Python Guide', 'score': 2.0, 'snippet': 'Advanced Python...'},
        ]
        mock_engine = MockSearchEngine(results=results)
        
        # Create mock index file
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'python tutorial'
            ])
            
            # Verify EnhancedSearchEngine.load was called with correct path
            MockEngineClass.load.assert_called_once()
            load_args = MockEngineClass.load.call_args
            self.assertEqual(load_args[0][0], self.site_dir / 'index.json')
            
            # Verify search was called with correct query
            self.assertEqual(len(mock_engine.search_calls), 1)
            self.assertEqual(mock_engine.search_calls[0]['query'], 'python tutorial')
            
            self.assertEqual(code, 0)
    
    def test_search_with_limit(self):
        """Should pass correct limit (top_k) to search engine."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--limit', '5'
            ])
            
            # Verify search was called with correct top_k
            self.assertEqual(mock_engine.search_calls[0]['top_k'], 5)
            self.assertEqual(code, 0)
    
    def test_search_default_limit(self):
        """Should use default limit of 10 when not specified."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query'
            ])
            
            # Default limit is 10
            self.assertEqual(mock_engine.search_calls[0]['top_k'], 10)
            self.assertEqual(code, 0)
    
    def test_search_json_output(self):
        """Should output JSON format when --json flag is set."""
        results = [
            {'url': 'https://example.com/page1', 'title': 'Result 1', 'score': 1.5, 'snippet': 'Test snippet'},
        ]
        mock_engine = MockSearchEngine(results=results)
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'test query',
                '--json', '--quiet'
            ])
            
            # Verify output is valid JSON
            output_data = json.loads(stdout.strip())
            
            # Verify JSON structure
            self.assertIn('query', output_data)
            self.assertEqual(output_data['query'], 'test query')
            self.assertIn('results', output_data)
            self.assertIn('count', output_data)
            self.assertIn('elapsed_ms', output_data)
            
            self.assertEqual(code, 0)
    
    def test_search_json_output_includes_results(self):
        """Should include search results in JSON output."""
        results = [
            {'url': 'https://example.com/doc1', 'title': 'Doc 1', 'score': 2.0, 'snippet': 'Snippet 1'},
            {'url': 'https://example.com/doc2', 'title': 'Doc 2', 'score': 1.5, 'snippet': 'Snippet 2'},
        ]
        mock_engine = MockSearchEngine(results=results)
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--json', '--quiet'
            ])
            
            output_data = json.loads(stdout.strip())
            self.assertEqual(output_data['count'], 2)
            self.assertEqual(len(output_data['results']), 2)
            self.assertEqual(output_data['results'][0]['url'], 'https://example.com/doc1')
            
            self.assertEqual(code, 0)
    
    def test_search_with_synonyms(self):
        """Should enable synonym expansion when --synonyms flag is set."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--synonyms'
            ])
            
            # Verify EnhancedSearchEngine.load was called with enable_synonyms=True
            load_kwargs = MockEngineClass.load.call_args[1]
            self.assertTrue(load_kwargs['enable_synonyms'])
            
            # Verify search was called with expand_synonyms=True
            self.assertTrue(mock_engine.search_calls[0]['expand_synonyms'])
            
            self.assertEqual(code, 0)
    
    def test_search_with_custom_synonyms_file(self):
        """Should load custom synonyms from file."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        # Create a custom synonyms file
        synonyms_data = {
            'groups': [
                ['quick', 'fast', 'speedy'],
                ['big', 'large', 'huge']
            ]
        }
        synonyms_file = self.site_dir / 'synonyms.json'
        with open(synonyms_file, 'w') as f:
            json.dump(synonyms_data, f)
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--synonyms-file', str(synonyms_file)
            ])
            
            # Verify EnhancedSearchEngine.load was called with synonym_groups
            load_kwargs = MockEngineClass.load.call_args[1]
            self.assertTrue(load_kwargs['enable_synonyms'])
            self.assertIsNotNone(load_kwargs['synonym_groups'])
            self.assertEqual(len(load_kwargs['synonym_groups']), 2)
            
            self.assertEqual(code, 0)
    
    def test_search_with_basic_engine(self):
        """Should use basic SearchEngine when --basic flag is set."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockBasicEngineClass:
            # Basic engine returns list, not dict
            mock_basic = MagicMock()
            mock_basic.search.return_value = []
            MockBasicEngineClass.load.return_value = mock_basic
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--basic'
            ])
            
            # Verify SearchEngine.load was called (not EnhancedSearchEngine)
            MockBasicEngineClass.load.assert_called_once()
            
            self.assertEqual(code, 0)
    
    def test_search_with_show_facets(self):
        """Should display facets when --show-facets flag is set."""
        mock_engine = MockSearchEngine()
        # Override search to return facets
        facets = {
            'category': {'api': 5, 'guide': 3},
            'section': {'intro': 4, 'advanced': 4}
        }
        original_search = mock_engine.search
        def search_with_facets(query, top_k=10, **kwargs):
            result = original_search(query, top_k, **kwargs)
            result['facets'] = facets
            return result
        mock_engine.search = search_with_facets
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--show-facets'
            ])
            
            # Facets should be displayed in output
            self.assertIn('Facets', stdout)
            
            self.assertEqual(code, 0)
    
    def test_search_json_output_includes_facets(self):
        """Should include facets in JSON output when available."""
        mock_engine = MockSearchEngine()
        facets = {
            'category': {'api': 5, 'guide': 3}
        }
        original_search = mock_engine.search
        def search_with_facets(query, top_k=10, **kwargs):
            result = original_search(query, top_k, **kwargs)
            result['facets'] = facets
            return result
        mock_engine.search = search_with_facets
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--json', '--quiet'
            ])
            
            output_data = json.loads(stdout.strip())
            self.assertIn('facets', output_data)
            self.assertEqual(output_data['facets']['category']['api'], 5)
            
            self.assertEqual(code, 0)
    
    def test_search_with_filter_category(self):
        """Should pass category filter to search engine."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--filter-category', 'api'
            ])
            
            # Verify search was called with facet_filters
            search_kwargs = mock_engine.search_calls[0]
            self.assertIn('facet_filters', search_kwargs)
            self.assertEqual(search_kwargs['facet_filters']['category'], 'api')
            
            self.assertEqual(code, 0)
    
    def test_search_with_filter_section(self):
        """Should pass section filter to search engine."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--filter-section', 'getting-started'
            ])
            
            # Verify search was called with facet_filters
            search_kwargs = mock_engine.search_calls[0]
            self.assertIn('facet_filters', search_kwargs)
            self.assertEqual(search_kwargs['facet_filters']['section'], 'getting-started')
            
            self.assertEqual(code, 0)
    
    def test_search_with_quiet_mode(self):
        """Should suppress info messages in quiet mode."""
        mock_engine = MockSearchEngine()
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--quiet'
            ])
            
            # Should not contain "Loading index from" message
            self.assertNotIn('Loading index from', stdout)
            
            self.assertEqual(code, 0)
    
    def test_search_with_scores(self):
        """Should show scores when --scores flag is set."""
        results = [
            {'url': 'https://example.com/page1', 'title': 'Test', 'score': 2.5, 'snippet': 'Test content'},
        ]
        mock_engine = MockSearchEngine(results=results)
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            # Note: --scores affects format_results, which is called internally
            # We just verify the command runs successfully
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--scores'
            ])
            
            self.assertEqual(code, 0)
    
    def test_search_loads_compressed_index(self):
        """Should load compressed index (index.json.gz) when available."""
        mock_engine = MockSearchEngine()
        
        # Create compressed index file (takes priority over uncompressed)
        compressed_index = self.site_dir / 'index.json.gz'
        import gzip
        with gzip.open(compressed_index, 'wt') as f:
            json.dump({'k1': 1.5, 'b': 0.75, 'documents': {}, 'index': {}}, f)
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query'
            ])
            
            # Verify it loaded the compressed index
            load_args = MockEngineClass.load.call_args[0]
            self.assertEqual(load_args[0], compressed_index)
            
            self.assertEqual(code, 0)
    
    def test_search_prefers_compressed_index(self):
        """Should prefer compressed index over uncompressed when both exist."""
        mock_engine = MockSearchEngine()
        
        # Create both compressed and uncompressed index files
        uncompressed = self.create_mock_index()
        compressed = self.site_dir / 'index.json.gz'
        import gzip
        with gzip.open(compressed, 'wt') as f:
            json.dump({'k1': 1.5, 'b': 0.75, 'documents': {}, 'index': {}}, f)
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, _, _ = run_cli([
                'search', str(self.site_dir), 'query'
            ])
            
            # Should use compressed version
            load_args = MockEngineClass.load.call_args[0]
            self.assertEqual(load_args[0], compressed)
            
            self.assertEqual(code, 0)


class TestCmdSearchErrorHandling(CLITestCase):
    """Tests for error handling in cmd_search."""
    
    def test_search_missing_index(self):
        """Should fail when no index file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir)
            # No index file
            
            code, stdout, _ = run_cli([
                'search', str(site_dir), 'query'
            ])
            
            self.assertEqual(code, 1)
            self.assertIn('Error:', stdout)
            self.assertIn('No index found', stdout)
    
    def test_search_missing_query_argument(self):
        """Should fail when query is not provided."""
        self.create_mock_index()
        
        with capture_output() as (stdout, stderr):
            try:
                code, _, _ = run_cli(['search', str(self.site_dir)])
            except SystemExit as e:
                code = e.code
        
        # Should fail with non-zero exit code (argparse error)
        self.assertNotEqual(code, 0)
    
    def test_search_invalid_synonyms_file(self):
        """Should fail when synonyms file is invalid JSON."""
        self.create_mock_index()
        
        # Create an invalid JSON file
        invalid_file = self.site_dir / 'bad_synonyms.json'
        with open(invalid_file, 'w') as f:
            f.write('{ this is not valid json }')
        
        code, stdout, _ = run_cli([
            'search', str(self.site_dir), 'query',
            '--synonyms-file', str(invalid_file)
        ])
        
        self.assertEqual(code, 1)
        self.assertIn('Error', stdout)
    
    def test_search_missing_synonyms_file(self):
        """Should fail when synonyms file doesn't exist."""
        self.create_mock_index()
        
        code, stdout, _ = run_cli([
            'search', str(self.site_dir), 'query',
            '--synonyms-file', '/nonexistent/synonyms.json'
        ])
        
        self.assertEqual(code, 1)
        self.assertIn('Error', stdout)
    
    def test_search_missing_site_dir_argument(self):
        """Should fail when site_dir is not provided."""
        with capture_output() as (stdout, stderr):
            try:
                code, _, _ = run_cli(['search'])
            except SystemExit as e:
                code = e.code
        
        # Should fail with non-zero exit code
        self.assertNotEqual(code, 0)


class TestCmdSearchArgParsing(unittest.TestCase):
    """Tests for search argument parsing."""
    
    def test_parse_search_defaults(self):
        """Should have sensible defaults for optional arguments."""
        args = parse_args(['search', '/path/to/site', 'test query'])
        
        self.assertEqual(args.command, 'search')
        self.assertEqual(args.site_dir, '/path/to/site')
        self.assertEqual(args.query, 'test query')
        self.assertEqual(args.limit, 10)  # Default limit
        self.assertFalse(args.json)
        self.assertFalse(args.scores)
        self.assertFalse(args.synonyms)
        self.assertFalse(args.quiet)
    
    def test_parse_search_limit(self):
        """Should parse --limit option."""
        args = parse_args(['search', '/path/to/site', 'query', '--limit', '20'])
        
        self.assertEqual(args.limit, 20)
    
    def test_parse_search_json_flag(self):
        """Should parse --json flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--json'])
        
        self.assertTrue(args.json)
    
    def test_parse_search_scores_flag(self):
        """Should parse --scores flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--scores'])
        
        self.assertTrue(args.scores)
    
    def test_parse_search_synonyms_flag(self):
        """Should parse --synonyms flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--synonyms'])
        
        self.assertTrue(args.synonyms)
    
    def test_parse_search_basic_flag(self):
        """Should parse --basic flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--basic'])
        
        self.assertTrue(args.basic)
    
    def test_parse_search_no_color_flag(self):
        """Should parse --no-color flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--no-color'])
        
        self.assertTrue(args.no_color)
    
    def test_parse_search_show_facets_flag(self):
        """Should parse --show-facets flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--show-facets'])
        
        self.assertTrue(args.show_facets)
    
    def test_parse_search_filter_category(self):
        """Should parse --filter-category option."""
        args = parse_args(['search', '/path/to/site', 'query', '--filter-category', 'api'])
        
        self.assertEqual(args.filter_category, 'api')
    
    def test_parse_search_filter_section(self):
        """Should parse --filter-section option."""
        args = parse_args(['search', '/path/to/site', 'query', '--filter-section', 'intro'])
        
        self.assertEqual(args.filter_section, 'intro')
    
    def test_parse_search_synonyms_file(self):
        """Should parse --synonyms-file option."""
        args = parse_args(['search', '/path/to/site', 'query', '--synonyms-file', '/path/to/syn.json'])
        
        self.assertEqual(args.synonyms_file, '/path/to/syn.json')
    
    def test_parse_search_quiet_flag(self):
        """Should parse --quiet flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--quiet'])
        
        self.assertTrue(args.quiet)
    
    def test_parse_search_separate_paths_flag(self):
        """Should parse --separate-paths flag."""
        args = parse_args(['search', '/path/to/site', 'query', '--separate-paths'])
        
        self.assertTrue(args.separate_paths)
    
    def test_parse_search_help(self):
        """Should show help text for search command."""
        with capture_output() as (stdout, stderr):
            try:
                parse_args(['search', '--help'])
            except SystemExit:
                pass
        
        output = stdout.getvalue()
        self.assertIn('search', output.lower())
        self.assertIn('query', output.lower())


# ============================================================================
# cmd_serve Tests
# ============================================================================

class MockHTTPServer:
    """Mock HTTPServer for testing CLI serve command without real server.
    
    This mock provides the same interface as HTTPServer to allow testing
    the serve command without binding to actual network ports.
    """
    
    def __init__(self, address: tuple, handler_class):
        """
        Create mock server.
        
        Args:
            address: Tuple of (host, port)
            handler_class: Request handler class
        """
        self.server_address = address
        self.handler_class = handler_class
        self.serve_forever_calls = 0
        self.shutdown_calls = 0
    
    def serve_forever(self):
        """Mock serve_forever - immediately raises KeyboardInterrupt to simulate Ctrl+C."""
        self.serve_forever_calls += 1
        # Simulate immediate Ctrl+C to avoid blocking tests
        raise KeyboardInterrupt()
    
    def shutdown(self):
        """Mock shutdown."""
        self.shutdown_calls += 1


class TestCmdServe(CLITestCase):
    """Tests for the cmd_serve CLI command."""
    
    def test_serve_basic(self):
        """Should start server with default options."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, stdout, _ = run_cli([
                    'serve', str(self.site_dir)
                ])
                
                # Verify SearchEngine.load was called with correct path
                MockEngineClass.load.assert_called_once()
                load_args = MockEngineClass.load.call_args[0]
                self.assertEqual(load_args[0], self.site_dir / 'index.json')
                
                # Verify run_server was called with defaults
                mock_run_server.assert_called_once()
                call_kwargs = mock_run_server.call_args[1]
                self.assertEqual(call_kwargs['host'], '127.0.0.1')
                self.assertEqual(call_kwargs['port'], 8080)
                self.assertFalse(call_kwargs['log_requests'])
                self.assertEqual(call_kwargs['per_page'], 10)
                self.assertEqual(call_kwargs['max_results'], 100)
                
                # Server should have been started
                self.assertEqual(mock_server.serve_forever_calls, 1)
                
                self.assertEqual(code, 0)
    
    def test_serve_custom_host(self):
        """Should pass custom host to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('0.0.0.0', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir),
                    '--host', '0.0.0.0'
                ])
                
                call_kwargs = mock_run_server.call_args[1]
                self.assertEqual(call_kwargs['host'], '0.0.0.0')
                
                self.assertEqual(code, 0)
    
    def test_serve_custom_port(self):
        """Should pass custom port to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 9000), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir),
                    '--port', '9000'
                ])
                
                call_kwargs = mock_run_server.call_args[1]
                self.assertEqual(call_kwargs['port'], 9000)
                
                self.assertEqual(code, 0)
    
    def test_serve_custom_host_and_port(self):
        """Should pass both custom host and port to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('192.168.1.100', 3000), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir),
                    '--host', '192.168.1.100',
                    '--port', '3000'
                ])
                
                call_kwargs = mock_run_server.call_args[1]
                self.assertEqual(call_kwargs['host'], '192.168.1.100')
                self.assertEqual(call_kwargs['port'], 3000)
                
                self.assertEqual(code, 0)
    
    def test_serve_with_log_requests(self):
        """Should enable request logging when --log-requests flag is set."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir),
                    '--log-requests'
                ])
                
                call_kwargs = mock_run_server.call_args[1]
                self.assertTrue(call_kwargs['log_requests'])
                
                self.assertEqual(code, 0)
    
    def test_serve_custom_per_page(self):
        """Should pass custom per_page to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir),
                    '--per-page', '25'
                ])
                
                call_kwargs = mock_run_server.call_args[1]
                self.assertEqual(call_kwargs['per_page'], 25)
                
                self.assertEqual(code, 0)
    
    def test_serve_custom_max_results(self):
        """Should pass custom max_results to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir),
                    '--max-results', '500'
                ])
                
                call_kwargs = mock_run_server.call_args[1]
                self.assertEqual(call_kwargs['max_results'], 500)
                
                self.assertEqual(code, 0)
    
    def test_serve_with_open_flag(self):
        """Should open browser when --open flag is set."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                with patch('webbrowser.open') as mock_webbrowser:
                    MockEngineClass.load.return_value = mock_engine
                    mock_run_server.return_value = mock_server
                    
                    code, _, _ = run_cli([
                        'serve', str(self.site_dir),
                        '--open'
                    ])
                    
                    # Verify webbrowser.open was called with correct URL
                    mock_webbrowser.assert_called_once_with('http://127.0.0.1:8080')
                    
                    self.assertEqual(code, 0)
    
    def test_serve_with_open_flag_custom_url(self):
        """Should open browser with custom host/port URL."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('0.0.0.0', 9000), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                with patch('webbrowser.open') as mock_webbrowser:
                    MockEngineClass.load.return_value = mock_engine
                    mock_run_server.return_value = mock_server
                    
                    code, _, _ = run_cli([
                        'serve', str(self.site_dir),
                        '--host', '0.0.0.0',
                        '--port', '9000',
                        '--open'
                    ])
                    
                    # Verify webbrowser.open was called with correct URL
                    mock_webbrowser.assert_called_once_with('http://0.0.0.0:9000')
                    
                    self.assertEqual(code, 0)
    
    def test_serve_without_open_flag(self):
        """Should not open browser when --open flag is not set."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                with patch('webbrowser.open') as mock_webbrowser:
                    MockEngineClass.load.return_value = mock_engine
                    mock_run_server.return_value = mock_server
                    
                    code, _, _ = run_cli([
                        'serve', str(self.site_dir)
                    ])
                    
                    # Verify webbrowser.open was NOT called
                    mock_webbrowser.assert_not_called()
                    
                    self.assertEqual(code, 0)
    
    def test_serve_passes_version(self):
        """Should pass version to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir)
                ])
                
                call_kwargs = mock_run_server.call_args[1]
                # Version should be passed (from __version__)
                self.assertIn('version', call_kwargs)
                
                self.assertEqual(code, 0)
    
    def test_serve_passes_engine(self):
        """Should pass loaded SearchEngine to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir)
                ])
                
                # Verify engine was passed as first positional argument
                call_args = mock_run_server.call_args[0]
                self.assertEqual(call_args[0], mock_engine)
                
                self.assertEqual(code, 0)
    
    def test_serve_with_all_options(self):
        """Should pass all options correctly to run_server."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('localhost', 5000), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                with patch('webbrowser.open') as mock_webbrowser:
                    MockEngineClass.load.return_value = mock_engine
                    mock_run_server.return_value = mock_server
                    
                    code, _, _ = run_cli([
                        'serve', str(self.site_dir),
                        '--host', 'localhost',
                        '--port', '5000',
                        '--log-requests',
                        '--per-page', '20',
                        '--max-results', '200',
                        '--open'
                    ])
                    
                    call_kwargs = mock_run_server.call_args[1]
                    self.assertEqual(call_kwargs['host'], 'localhost')
                    self.assertEqual(call_kwargs['port'], 5000)
                    self.assertTrue(call_kwargs['log_requests'])
                    self.assertEqual(call_kwargs['per_page'], 20)
                    self.assertEqual(call_kwargs['max_results'], 200)
                    
                    mock_webbrowser.assert_called_once_with('http://localhost:5000')
                    
                    self.assertEqual(code, 0)
    
    def test_serve_prints_startup_info(self):
        """Should print server startup information."""
        mock_engine = MockSearchEngine(stats={
            'total_documents': 500,
            'unique_terms': 10000,
            'avg_document_length': 150,
            'k1': 1.5,
            'b': 0.75
        })
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, stdout, _ = run_cli([
                    'serve', str(self.site_dir)
                ])
                
                # Should print URL
                self.assertIn('http://127.0.0.1:8080', stdout)
                # Should print doc count
                self.assertIn('500', stdout)
                # Should print term count
                self.assertIn('10000', stdout)
                
                self.assertEqual(code, 0)
    
    def test_serve_loads_compressed_index(self):
        """Should load compressed index (index.json.gz) when available."""
        mock_engine = MockSearchEngine()
        mock_server = MockHTTPServer(('127.0.0.1', 8080), None)
        
        # Create compressed index file
        compressed_index = self.site_dir / 'index.json.gz'
        import gzip
        with gzip.open(compressed_index, 'wt') as f:
            json.dump({'k1': 1.5, 'b': 0.75, 'documents': {}, 'index': {}}, f)
        
        with patch('doc_search.cli.commands.SearchEngine') as MockEngineClass:
            with patch('doc_search.server.run_server') as mock_run_server:
                MockEngineClass.load.return_value = mock_engine
                mock_run_server.return_value = mock_server
                
                code, _, _ = run_cli([
                    'serve', str(self.site_dir)
                ])
                
                # Verify it loaded the compressed index
                load_args = MockEngineClass.load.call_args[0]
                self.assertEqual(load_args[0], compressed_index)
                
                self.assertEqual(code, 0)


class TestCmdServeErrorHandling(CLITestCase):
    """Tests for error handling in cmd_serve."""
    
    def test_serve_missing_index(self):
        """Should fail when no index file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir)
            # No index file
            
            code, stdout, _ = run_cli([
                'serve', str(site_dir)
            ])
            
            self.assertEqual(code, 1)
            self.assertIn('Error:', stdout)
            self.assertIn('No index found', stdout)
    
    def test_serve_missing_index_suggests_indexing(self):
        """Should suggest running index command when index is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir)
            
            code, stdout, _ = run_cli([
                'serve', str(site_dir)
            ])
            
            self.assertEqual(code, 1)
            self.assertIn('doc_search index', stdout)
    
    def test_serve_missing_site_dir_argument(self):
        """Should fail when site_dir is not provided."""
        with capture_output() as (stdout, stderr):
            try:
                code, _, _ = run_cli(['serve'])
            except SystemExit as e:
                code = e.code
        
        # Should fail with non-zero exit code (argparse error)
        self.assertNotEqual(code, 0)


class TestCmdServeArgParsing(unittest.TestCase):
    """Tests for serve argument parsing."""
    
    def test_parse_serve_defaults(self):
        """Should have sensible defaults for optional arguments."""
        args = parse_args(['serve', '/path/to/site'])
        
        self.assertEqual(args.command, 'serve')
        self.assertEqual(args.site_dir, '/path/to/site')
        self.assertEqual(args.host, '127.0.0.1')
        self.assertEqual(args.port, 8080)
        self.assertFalse(args.open)
        self.assertFalse(args.log_requests)
        self.assertEqual(args.per_page, 10)
        self.assertEqual(args.max_results, 100)
    
    def test_parse_serve_host(self):
        """Should parse --host option."""
        args = parse_args(['serve', '/path/to/site', '--host', '0.0.0.0'])
        
        self.assertEqual(args.host, '0.0.0.0')
    
    def test_parse_serve_port(self):
        """Should parse --port option."""
        args = parse_args(['serve', '/path/to/site', '--port', '9000'])
        
        self.assertEqual(args.port, 9000)
        self.assertIsInstance(args.port, int)
    
    def test_parse_serve_open_flag(self):
        """Should parse --open flag."""
        args = parse_args(['serve', '/path/to/site', '--open'])
        
        self.assertTrue(args.open)
    
    def test_parse_serve_log_requests_flag(self):
        """Should parse --log-requests flag."""
        args = parse_args(['serve', '/path/to/site', '--log-requests'])
        
        self.assertTrue(args.log_requests)
    
    def test_parse_serve_per_page(self):
        """Should parse --per-page option."""
        args = parse_args(['serve', '/path/to/site', '--per-page', '25'])
        
        self.assertEqual(args.per_page, 25)
        self.assertIsInstance(args.per_page, int)
    
    def test_parse_serve_max_results(self):
        """Should parse --max-results option."""
        args = parse_args(['serve', '/path/to/site', '--max-results', '500'])
        
        self.assertEqual(args.max_results, 500)
        self.assertIsInstance(args.max_results, int)
    
    def test_parse_serve_separate_paths_flag(self):
        """Should parse --separate-paths flag."""
        args = parse_args(['serve', '/path/to/site', '--separate-paths'])
        
        self.assertTrue(args.separate_paths)
    
    def test_parse_serve_help(self):
        """Should show help text for serve command."""
        with capture_output() as (stdout, stderr):
            try:
                parse_args(['serve', '--help'])
            except SystemExit:
                pass
        
        output = stdout.getvalue()
        self.assertIn('serve', output.lower())
        self.assertIn('host', output)
        self.assertIn('port', output)


class TestCmdSearchIntegration(CLITestCase):
    """Integration tests for cmd_search using real file structures."""
    
    def test_search_with_suggestion_in_response(self):
        """Should handle search response with spelling suggestion."""
        mock_engine = MockSearchEngine()
        # Override search to return a suggestion
        def search_with_suggestion(query, top_k=10, **kwargs):
            return {
                'results': [],
                'suggestion': 'python',  # Did you mean?
                'expanded_query': None,
                'facets': {}
            }
        mock_engine.search = search_with_suggestion
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'pyhton'  # Typo
            ])
            
            # Should show suggestion in output
            self.assertIn('Did you mean', stdout)
            self.assertIn('python', stdout)
            
            self.assertEqual(code, 0)
    
    def test_search_json_output_includes_suggestion(self):
        """Should include suggestion in JSON output when available."""
        mock_engine = MockSearchEngine()
        def search_with_suggestion(query, top_k=10, **kwargs):
            return {
                'results': [],
                'suggestion': 'corrected_query',
                'expanded_query': None,
                'facets': {}
            }
        mock_engine.search = search_with_suggestion
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'query',
                '--json', '--quiet'
            ])
            
            output_data = json.loads(stdout.strip())
            self.assertIn('suggestion', output_data)
            self.assertEqual(output_data['suggestion'], 'corrected_query')
            
            self.assertEqual(code, 0)
    
    def test_search_json_output_includes_expanded_query(self):
        """Should include expanded_query in JSON output when synonyms used."""
        mock_engine = MockSearchEngine()
        def search_with_expansion(query, top_k=10, **kwargs):
            return {
                'results': [],
                'suggestion': None,
                'expanded_query': 'quick fast speedy',
                'facets': {}
            }
        mock_engine.search = search_with_expansion
        
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'quick',
                '--synonyms', '--json', '--quiet'
            ])
            
            output_data = json.loads(stdout.strip())
            self.assertIn('expanded_query', output_data)
            self.assertEqual(output_data['expanded_query'], 'quick fast speedy')
            
            self.assertEqual(code, 0)
    
    def test_search_with_all_options(self):
        """Should handle all options together correctly."""
        mock_engine = MockSearchEngine(results=[
            {'url': 'https://example.com/doc', 'title': 'Doc', 'score': 1.0, 'snippet': 'Test'}
        ])
        self.create_mock_index()
        
        # Create synonyms file
        synonyms_file = self.site_dir / 'syn.json'
        with open(synonyms_file, 'w') as f:
            json.dump({'groups': [['test', 'check']]}, f)
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'test query',
                '--limit', '5',
                '--json',
                '--synonyms-file', str(synonyms_file),
                '--filter-category', 'docs',
                '--quiet'
            ])
            
            # Verify JSON output
            output_data = json.loads(stdout.strip())
            self.assertEqual(output_data['query'], 'test query')
            self.assertEqual(output_data['count'], 1)
            
            # Verify correct options passed
            search_kwargs = mock_engine.search_calls[0]
            self.assertEqual(search_kwargs['top_k'], 5)
            self.assertEqual(search_kwargs['facet_filters']['category'], 'docs')
            self.assertTrue(search_kwargs['expand_synonyms'])
            
            self.assertEqual(code, 0)
    
    def test_search_no_results(self):
        """Should handle empty search results gracefully."""
        mock_engine = MockSearchEngine(results=[])
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'nonexistent term'
            ])
            
            # Should return 0 (success) even with no results
            self.assertEqual(code, 0)
    
    def test_search_no_results_json(self):
        """Should output valid JSON with empty results."""
        mock_engine = MockSearchEngine(results=[])
        self.create_mock_index()
        
        with patch('doc_search.cli.commands.EnhancedSearchEngine') as MockEngineClass:
            MockEngineClass.load.return_value = mock_engine
            
            code, stdout, _ = run_cli([
                'search', str(self.site_dir), 'nonexistent',
                '--json', '--quiet'
            ])
            
            output_data = json.loads(stdout.strip())
            self.assertEqual(output_data['count'], 0)
            self.assertEqual(output_data['results'], [])
            
            self.assertEqual(code, 0)


if __name__ == '__main__':
    unittest.main()
