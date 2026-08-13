"""
Integration tests for the full crawl → index → search workflow.

Tests end-to-end functionality using mock HTTP responses to avoid
hitting real URLs during testing.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import URLError, HTTPError
import urllib.request

from doc_search.crawler import Crawler
from doc_search.indexer import BM25Index
from doc_search.searcher import SearchEngine, EnhancedSearchEngine


class MockResponse:
    """Mock HTTP response for testing."""
    
    def __init__(self, content: str, content_type: str = 'text/html', 
                 status: int = 200, headers: dict = None):
        self.content = content.encode('utf-8')
        self.content_type = content_type
        self.status = status
        self._headers = headers or {}
    
    def read(self):
        return self.content
    
    @property
    def headers(self):
        class Headers:
            def __init__(self, h, ct):
                self._headers = h
                self._content_type = ct
            def get(self, key, default=''):
                if key == 'Content-Type':
                    return self._content_type
                return self._headers.get(key, default)
        return Headers(self._headers, self.content_type)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


# Sample HTML pages for testing
MOCK_PAGES = {
    'https://example.com/': '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Example Documentation</title>
        <meta name="description" content="Welcome to Example docs">
    </head>
    <body>
        <h1>Welcome to Example</h1>
        <p>This is the main documentation page for Example project.</p>
        <p>Learn about Python programming and web development.</p>
        <a href="/getting-started">Getting Started</a>
        <a href="/api-reference">API Reference</a>
        <a href="/tutorials">Tutorials</a>
    </body>
    </html>
    ''',
    
    'https://example.com/getting-started': '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Getting Started - Example</title>
        <meta name="description" content="Quick start guide">
    </head>
    <body>
        <h1>Getting Started</h1>
        <h2>Installation</h2>
        <p>Install Example using pip:</p>
        <pre>pip install example</pre>
        <h2>Configuration</h2>
        <p>Configure your project settings in config.yaml file.</p>
        <p>Python version 3.8 or higher is required.</p>
        <a href="/">Home</a>
        <a href="/tutorials">Tutorials</a>
    </body>
    </html>
    ''',
    
    'https://example.com/api-reference': '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>API Reference - Example</title>
        <meta name="description" content="Complete API documentation">
    </head>
    <body>
        <h1>API Reference</h1>
        <h2>Core Functions</h2>
        <p>The main function is example.run() which starts the application.</p>
        <h3>example.run()</h3>
        <p>Runs the application with default configuration.</p>
        <h3>example.configure()</h3>
        <p>Configures the application settings programmatically.</p>
        <a href="/">Home</a>
    </body>
    </html>
    ''',
    
    'https://example.com/tutorials': '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tutorials - Example</title>
        <meta name="description" content="Step-by-step tutorials">
    </head>
    <body>
        <h1>Tutorials</h1>
        <h2>Basic Tutorial</h2>
        <p>Learn the basics of using Example in your Python projects.</p>
        <p>This tutorial covers list comprehension and data processing.</p>
        <h2>Advanced Tutorial</h2>
        <p>Advanced topics including async programming and optimization.</p>
        <a href="/">Home</a>
        <a href="/getting-started">Getting Started</a>
    </body>
    </html>
    ''',
    
    # Robots.txt
    'https://example.com/robots.txt': '''
User-agent: *
Allow: /
Crawl-delay: 0
    '''
}


def mock_urlopen(request, timeout=None, context=None):
    """Mock urlopen that returns predefined content for known URLs."""
    url = request.full_url if hasattr(request, 'full_url') else str(request)
    
    # Normalize URL (remove trailing slash for matching)
    url_normalized = url.rstrip('/')
    
    for mock_url, content in MOCK_PAGES.items():
        mock_url_normalized = mock_url.rstrip('/')
        if url_normalized == mock_url_normalized or url == mock_url:
            return MockResponse(content)
    
    # Return 404 for unknown URLs
    raise HTTPError(url, 404, 'Not Found', {}, None)


class TestCrawlIndexSearchWorkflow(unittest.TestCase):
    """Test the complete crawl → index → search workflow."""
    
    def setUp(self):
        """Create a temporary directory for test data."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('urllib.request.urlopen', mock_urlopen)
    @patch('doc_search.crawler.fetcher.urlopen', mock_urlopen)
    def test_full_workflow_crawl_index_search(self):
        """Test complete workflow: crawl mock site → build index → search."""
        # Step 1: Crawl mock site
        crawler = Crawler(
            base_url='https://example.com/',
            data_dir=self.data_dir,
            delay=0,  # No delay for tests
            timeout=5,
            max_pages=10,
            verbose=False
        )
        
        stats = crawler.crawl(resume=False)
        
        # Verify crawl completed successfully
        self.assertGreater(stats['pages_crawled'], 0)
        self.assertEqual(stats['pages_failed'], 0)
        
        # Step 2: Build index from crawled pages
        index = BM25Index()
        pages_dir = self.data_dir / 'pages'
        doc_count = index.build_from_pages(pages_dir, verbose=False)
        
        # Verify index was built
        self.assertGreater(doc_count, 0)
        self.assertEqual(doc_count, index.total_docs)
        
        # Step 3: Search and verify results
        engine = SearchEngine(index, pages_dir)
        
        # Test basic search
        results = engine.search('python', top_k=5)
        self.assertGreater(len(results), 0)
        
        # Test that search finds expected content
        results = engine.search('installation pip', top_k=5)
        self.assertGreater(len(results), 0)
        # Getting Started page should rank high for "installation pip"
        urls = [r['url'] for r in results]
        self.assertTrue(
            any('getting-started' in url for url in urls),
            f"Expected 'getting-started' in results for 'installation pip', got: {urls}"
        )
        
        # Test API search
        results = engine.search('API reference function', top_k=5)
        self.assertGreater(len(results), 0)
        urls = [r['url'] for r in results]
        self.assertTrue(
            any('api-reference' in url for url in urls),
            f"Expected 'api-reference' in results for 'API reference', got: {urls}"
        )
        
        # Test tutorials search
        results = engine.search('tutorial list comprehension', top_k=5)
        self.assertGreater(len(results), 0)
        urls = [r['url'] for r in results]
        self.assertTrue(
            any('tutorial' in url for url in urls),
            f"Expected 'tutorials' in results, got: {urls}"
        )
    
    @patch('urllib.request.urlopen', mock_urlopen)
    @patch('doc_search.crawler.fetcher.urlopen', mock_urlopen)
    def test_index_persistence_save_load(self):
        """Test index save/load round-trip."""
        # Crawl and build index
        crawler = Crawler(
            base_url='https://example.com/',
            data_dir=self.data_dir,
            delay=0,
            max_pages=10,
            verbose=False
        )
        crawler.crawl(resume=False)
        
        index = BM25Index()
        pages_dir = self.data_dir / 'pages'
        index.build_from_pages(pages_dir, verbose=False)
        
        # Save index
        index_path = self.data_dir / 'index.json'
        saved_path = index.save(index_path, compress=True)
        self.assertTrue(saved_path.exists())
        
        # Load index
        loaded_index = BM25Index.load(saved_path)
        
        # Verify loaded index matches original
        self.assertEqual(loaded_index.total_docs, index.total_docs)
        self.assertEqual(loaded_index.k1, index.k1)
        self.assertEqual(loaded_index.b, index.b)
        self.assertEqual(len(loaded_index.documents), len(index.documents))
        self.assertEqual(len(loaded_index.index), len(index.index))
        
        # Search with loaded index should return same results
        original_results = index.search('python installation', top_k=5)
        loaded_results = loaded_index.search('python installation', top_k=5)
        
        self.assertEqual(len(original_results), len(loaded_results))
        for orig, loaded in zip(original_results, loaded_results):
            self.assertEqual(orig['url'], loaded['url'])
            self.assertAlmostEqual(orig['score'], loaded['score'], places=4)
    
    @patch('urllib.request.urlopen', mock_urlopen)
    @patch('doc_search.crawler.fetcher.urlopen', mock_urlopen)
    def test_index_uncompressed_save_load(self):
        """Test uncompressed index save/load."""
        # Crawl and build index
        crawler = Crawler(
            base_url='https://example.com/',
            data_dir=self.data_dir,
            delay=0,
            max_pages=5,
            verbose=False
        )
        crawler.crawl(resume=False)
        
        index = BM25Index()
        pages_dir = self.data_dir / 'pages'
        index.build_from_pages(pages_dir, verbose=False)
        
        # Save uncompressed
        index_path = self.data_dir / 'index_uncompressed.json'
        index.save(index_path, compress=False)
        self.assertTrue(index_path.exists())
        
        # Load and verify
        loaded_index = BM25Index.load(index_path)
        self.assertEqual(loaded_index.total_docs, index.total_docs)
    
    @patch('urllib.request.urlopen', mock_urlopen)
    @patch('doc_search.crawler.fetcher.urlopen', mock_urlopen)
    def test_enhanced_search_engine(self):
        """Test EnhancedSearchEngine with full workflow."""
        # Crawl and build index
        crawler = Crawler(
            base_url='https://example.com/',
            data_dir=self.data_dir,
            delay=0,
            max_pages=10,
            verbose=False
        )
        crawler.crawl(resume=False)
        
        index = BM25Index()
        pages_dir = self.data_dir / 'pages'
        index.build_from_pages(pages_dir, verbose=False)
        
        # Use enhanced search engine
        engine = EnhancedSearchEngine(
            index, 
            pages_dir,
            enable_spellcheck=True,
            enable_facets=True,
            enable_synonyms=False
        )
        
        # Test enhanced search (search returns list, search_enhanced returns dict)
        results = engine.search('python programming', top_k=5)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        
        # Test search_enhanced for full response with metadata
        response = engine.search_enhanced('python programming', top_k=5)
        self.assertIn('results', response)
        self.assertIn('suggestion', response)
        self.assertIn('facets', response)
        self.assertGreater(len(response['results']), 0)
        
        # Test title suggestions
        suggestions = engine.get_suggestions('pyt', max_suggestions=5)
        self.assertIsInstance(suggestions, list)

        # Test stats
        stats = engine.get_stats()
        self.assertIn('total_documents', stats)
        self.assertIn('features', stats)
        self.assertTrue(stats['features']['spellcheck'])


class TestCrawlerErrorHandling(unittest.TestCase):
    """Test error handling and propagation through the pipeline."""
    
    def setUp(self):
        """Create a temporary directory for test data."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_crawl_with_http_errors(self):
        """Test crawler handles HTTP errors gracefully."""
        def mock_urlopen_with_errors(request, timeout=None, context=None):
            url = request.full_url if hasattr(request, 'full_url') else str(request)
            
            if 'robots.txt' in url:
                return MockResponse('User-agent: *\nAllow: /')
            
            if 'example.com' in url and url.rstrip('/').endswith('example.com'):
                # Return valid home page with link to bad page
                return MockResponse('''
                    <html>
                    <head><title>Home</title></head>
                    <body>
                        <p>Welcome</p>
                        <a href="/bad-page">Bad Page</a>
                    </body>
                    </html>
                ''')
            
            if 'bad-page' in url:
                raise HTTPError(url, 500, 'Server Error', {}, None)
            
            raise HTTPError(url, 404, 'Not Found', {}, None)
        
        with patch('urllib.request.urlopen', mock_urlopen_with_errors), \
             patch('doc_search.crawler.fetcher.urlopen', mock_urlopen_with_errors):
            crawler = Crawler(
                base_url='https://example.com/',
                data_dir=self.data_dir,
                delay=0,
                max_pages=10,
                verbose=False
            )
            
            stats = crawler.crawl(resume=False)
            
            # Should have crawled some pages and recorded failures
            self.assertGreater(stats['pages_crawled'], 0)
            self.assertGreater(stats['pages_failed'], 0)
    
    def test_crawl_with_network_errors(self):
        """Test crawler handles network errors gracefully."""
        def mock_urlopen_network_error(request, timeout=None, context=None):
            url = request.full_url if hasattr(request, 'full_url') else str(request)
            
            if 'robots.txt' in url:
                return MockResponse('User-agent: *\nAllow: /')
            
            if 'example.com' in url and url.rstrip('/').endswith('example.com'):
                return MockResponse('''
                    <html>
                    <head><title>Home</title></head>
                    <body>
                        <p>Content about Python programming</p>
                        <a href="/network-error">Network Error Page</a>
                    </body>
                    </html>
                ''')
            
            if 'network-error' in url:
                raise URLError('Connection refused')
            
            raise HTTPError(url, 404, 'Not Found', {}, None)
        
        with patch('urllib.request.urlopen', mock_urlopen_network_error), \
             patch('doc_search.crawler.fetcher.urlopen', mock_urlopen_network_error):
            crawler = Crawler(
                base_url='https://example.com/',
                data_dir=self.data_dir,
                delay=0,
                max_pages=10,
                verbose=False
            )
            
            stats = crawler.crawl(resume=False)
            
            # Should complete without crashing
            self.assertGreater(stats['pages_crawled'], 0)
    
    def test_index_empty_pages_dir(self):
        """Test indexer handles empty pages directory."""
        # Create empty pages dir
        pages_dir = self.data_dir / 'pages'
        pages_dir.mkdir(parents=True)
        
        index = BM25Index()
        doc_count = index.build_from_pages(pages_dir, verbose=False)
        
        self.assertEqual(doc_count, 0)
        self.assertEqual(index.total_docs, 0)
    
    def test_index_malformed_json(self):
        """Test indexer handles malformed JSON files."""
        pages_dir = self.data_dir / 'pages'
        pages_dir.mkdir(parents=True)
        
        # Create valid page
        valid_page = {
            'url': 'https://example.com/valid',
            'title': 'Valid Page',
            'text': 'Valid content about Python',
            'description': 'A valid page',
            'headings': []
        }
        with open(pages_dir / 'valid.json', 'w') as f:
            json.dump(valid_page, f)
        
        # Create malformed JSON
        with open(pages_dir / 'malformed.json', 'w') as f:
            f.write('{ invalid json }}}')
        
        index = BM25Index()
        doc_count = index.build_from_pages(pages_dir, verbose=False)
        
        # Should index valid page and skip malformed
        self.assertEqual(doc_count, 1)
    
    def test_search_empty_index(self):
        """Test searching an empty index returns empty results."""
        index = BM25Index()
        results = index.search('python', top_k=10)
        
        self.assertEqual(results, [])
    
    def test_search_no_matches(self):
        """Test search with no matching terms."""
        index = BM25Index()
        index.add_document(
            doc_id=0,
            url='https://example.com/test',
            title='Test Page',
            text='This is about JavaScript and Node.js',
            description='A test page'
        )
        
        results = index.search('python django flask', top_k=10)
        self.assertEqual(results, [])


class TestCrawlerConfiguration(unittest.TestCase):
    """Test various crawler configuration options."""
    
    def setUp(self):
        """Create a temporary directory for test data."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('urllib.request.urlopen', mock_urlopen)
    @patch('doc_search.crawler.fetcher.urlopen', mock_urlopen)
    def test_max_pages_limit(self):
        """Test crawler respects max_pages limit."""
        crawler = Crawler(
            base_url='https://example.com/',
            data_dir=self.data_dir,
            delay=0,
            max_pages=2,
            verbose=False
        )
        
        stats = crawler.crawl(resume=False)
        
        self.assertLessEqual(stats['pages_crawled'], 2)
    
    @patch('urllib.request.urlopen', mock_urlopen)
    @patch('doc_search.crawler.fetcher.urlopen', mock_urlopen)
    def test_max_depth_limit(self):
        """Test crawler respects max_depth limit."""
        crawler = Crawler(
            base_url='https://example.com/',
            data_dir=self.data_dir,
            delay=0,
            max_depth=0,  # Only crawl start URL
            verbose=False
        )
        
        stats = crawler.crawl(resume=False)
        
        # Should only crawl the starting page
        self.assertEqual(stats['pages_crawled'], 1)
    
    @patch('urllib.request.urlopen', mock_urlopen)
    @patch('doc_search.crawler.fetcher.urlopen', mock_urlopen)
    def test_url_filter(self):
        """Test crawler respects custom URL filter."""
        def only_tutorials(url):
            return 'tutorial' in url.lower() or url.rstrip('/').endswith('example.com')
        
        crawler = Crawler(
            base_url='https://example.com/',
            data_dir=self.data_dir,
            delay=0,
            url_filter=only_tutorials,
            verbose=False
        )
        
        stats = crawler.crawl(resume=False)
        
        # Should crawl home and tutorials only
        self.assertGreater(stats['pages_crawled'], 0)
        
        # Check crawled pages
        pages_dir = self.data_dir / 'pages'
        for page_file in pages_dir.glob('*.json'):
            with open(page_file) as f:
                page = json.load(f)
            url = page['url']
            self.assertTrue(
                'tutorial' in url.lower() or url.rstrip('/').endswith('example.com'),
                f"Unexpected URL crawled: {url}"
            )


class TestSearchEngineFeatures(unittest.TestCase):
    """Test specific search engine features with indexed content."""
    
    def setUp(self):
        """Create index with test documents."""
        self.index = BM25Index()
        
        # Add test documents
        self.index.add_document(
            doc_id=0,
            url='https://example.com/python-basics',
            title='Python Basics',
            text='Learn Python programming basics. Variables, loops, and functions.',
            description='Introduction to Python'
        )
        
        self.index.add_document(
            doc_id=1,
            url='https://example.com/python-advanced',
            title='Advanced Python',
            text='Advanced Python topics. Decorators, generators, and metaclasses.',
            description='Advanced Python programming'
        )
        
        self.index.add_document(
            doc_id=2,
            url='https://example.com/javascript-intro',
            title='JavaScript Introduction',
            text='Learn JavaScript for web development. DOM manipulation and events.',
            description='Getting started with JavaScript'
        )
    
    def test_bm25_scoring(self):
        """Test BM25 scoring ranks relevant documents higher."""
        results = self.index.search('python programming', top_k=3)
        
        self.assertEqual(len(results), 2)  # Only Python docs should match
        
        # Python docs should be returned
        urls = [r['url'] for r in results]
        self.assertTrue(all('python' in url for url in urls))
        
        # JavaScript doc should not be returned
        self.assertFalse(any('javascript' in url for url in urls))
    
    def test_search_score_order(self):
        """Test search results are ordered by descending score."""
        results = self.index.search('python', top_k=10)
        
        scores = [r['score'] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
    
    def test_top_k_limit(self):
        """Test top_k limits number of results."""
        results = self.index.search('programming', top_k=1)
        self.assertLessEqual(len(results), 1)
    
    def test_search_engine_with_pages_dir(self):
        """Test SearchEngine with pages directory for snippets."""
        temp_dir = tempfile.mkdtemp()
        try:
            pages_dir = Path(temp_dir) / 'pages'
            pages_dir.mkdir()
            
            # Create page file
            page_data = {
                'url': 'https://example.com/test',
                'title': 'Test Page',
                'text': 'This is a test page about Python programming and list comprehension.',
                'description': 'Test description'
            }
            
            # Use the same filename format as the crawler
            from doc_search.utils import url_to_filename
            filename = url_to_filename(page_data['url']) + '.json'
            with open(pages_dir / filename, 'w') as f:
                json.dump(page_data, f)
            
            # Build index
            index = BM25Index()
            index.add_document(
                doc_id=0,
                url=page_data['url'],
                title=page_data['title'],
                text=page_data['text'],
                description=page_data['description']
            )
            
            # Create search engine with pages directory
            engine = SearchEngine(index, pages_dir)
            
            results = engine.search('python list comprehension', top_k=5)
            
            self.assertGreater(len(results), 0)
            # Should have snippet with highlighted terms
            result = results[0]
            self.assertIn('snippet', result)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_phrase_search(self):
        """Test phrase search functionality."""
        # Add document with exact phrase
        self.index.add_document(
            doc_id=3,
            url='https://example.com/list-comp',
            title='List Comprehension',
            text='Python list comprehension is a concise way to create lists.',
            description='About list comprehension'
        )
        
        temp_dir = tempfile.mkdtemp()
        try:
            pages_dir = Path(temp_dir) / 'pages'
            pages_dir.mkdir()
            
            # Create page file
            from doc_search.utils import url_to_filename
            page_data = {
                'url': 'https://example.com/list-comp',
                'title': 'List Comprehension',
                'text': 'Python list comprehension is a concise way to create lists.',
                'description': 'About list comprehension'
            }
            filename = url_to_filename(page_data['url']) + '.json'
            with open(pages_dir / filename, 'w') as f:
                json.dump(page_data, f)
            
            engine = SearchEngine(self.index, pages_dir)
            
            # Search for exact phrase
            results = engine.search('"list comprehension"', top_k=5)
            
            self.assertGreater(len(results), 0)
            # The list-comp page should be in results
            urls = [r['url'] for r in results]
            self.assertTrue(any('list-comp' in url for url in urls))
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_exact_phrase_rejects_stemmed_near_match(self):
        """Quoted / exact-match search must not accept stemmed bigrams."""
        self.index.add_document(
            doc_id=4,
            url='https://example.com/running-files',
            title='Running Files Guide',
            text='This document is about running files in production.',
            description='running files'
        )
        self.index.add_document(
            doc_id=5,
            url='https://example.com/run-a-file',
            title='How to run a file',
            text='You can run a file from the command line.',
            description='run a file'
        )
        self.index.add_document(
            doc_id=6,
            url='https://example.com/separate',
            title='Separate mentions',
            text='After running the tests, check the files in the output directory.',
            description='separate'
        )

        engine = SearchEngine(self.index)
        bag = engine.search('running files', top_k=10, snippet_length=0)
        bag_urls = {r['url'] for r in bag}
        self.assertIn('https://example.com/running-files', bag_urls)
        self.assertIn('https://example.com/run-a-file', bag_urls)

        exact = engine.search('"running files"', top_k=10, snippet_length=0)
        exact_urls = {r['url'] for r in exact}
        self.assertEqual(exact_urls, {'https://example.com/running-files'})


class TestIndexStats(unittest.TestCase):
    """Test index statistics and metadata."""
    
    def test_index_stats(self):
        """Test get_stats returns expected information."""
        index = BM25Index(k1=1.2, b=0.8, stem=True)
        
        index.add_document(
            doc_id=0,
            url='https://example.com/test',
            title='Test',
            text='Python programming tutorial'
        )
        
        stats = index.get_stats()
        
        self.assertEqual(stats['total_documents'], 1)
        self.assertGreater(stats['unique_terms'], 0)
        self.assertEqual(stats['k1'], 1.2)
        self.assertEqual(stats['b'], 0.8)
        self.assertTrue(stats['stemming'])
    
    def test_document_lookup(self):
        """Test document lookup by URL and ID."""
        index = BM25Index()
        
        index.add_document(
            doc_id=0,
            url='https://example.com/test',
            title='Test Page',
            text='Content',
            description='Description'
        )
        
        # Lookup by URL
        doc_id = index.get_doc_id('https://example.com/test')
        self.assertEqual(doc_id, 0)
        
        # Lookup by ID
        doc = index.get_document(0)
        self.assertEqual(doc['url'], 'https://example.com/test')
        self.assertEqual(doc['title'], 'Test Page')
        
        # Check URL existence
        self.assertTrue(index.has_url('https://example.com/test'))
        self.assertFalse(index.has_url('https://example.com/nonexistent'))


if __name__ == '__main__':
    unittest.main()
