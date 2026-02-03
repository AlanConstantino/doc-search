"""
Tests for the page processor module.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from doc_search.crawler.processor import (
    PageProcessor,
    content_hash,
    build_page_data,
    build_document_data,
)


# ============================================================================
# Test Standalone Functions
# ============================================================================

class TestContentHash(unittest.TestCase):
    """Tests for the content_hash function."""
    
    def test_hash_returns_string(self):
        """content_hash should return a string."""
        result = content_hash("Hello, World!")
        self.assertIsInstance(result, str)
    
    def test_hash_is_64_chars(self):
        """SHA256 hex digest should be 64 characters."""
        result = content_hash("test content")
        self.assertEqual(len(result), 64)
    
    def test_hash_is_deterministic(self):
        """Same content should produce same hash."""
        content = "The quick brown fox jumps over the lazy dog"
        hash1 = content_hash(content)
        hash2 = content_hash(content)
        self.assertEqual(hash1, hash2)
    
    def test_hash_differs_for_different_content(self):
        """Different content should produce different hash."""
        hash1 = content_hash("content A")
        hash2 = content_hash("content B")
        self.assertNotEqual(hash1, hash2)
    
    def test_hash_empty_string(self):
        """Empty string should produce a valid hash."""
        result = content_hash("")
        self.assertEqual(len(result), 64)
    
    def test_hash_unicode_content(self):
        """Unicode content should be handled correctly."""
        result = content_hash("Hello 世界 🌍")
        self.assertEqual(len(result), 64)
    
    def test_hash_known_value(self):
        """Known SHA256 hash value for verification."""
        # SHA256 of "Hello, World!" is known
        result = content_hash("Hello, World!")
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        self.assertEqual(result, expected)


class TestBuildPageData(unittest.TestCase):
    """Tests for the build_page_data function."""
    
    def test_basic_page_data(self):
        """build_page_data should return a dict with required fields."""
        extracted = {
            'text': 'Page content',
            'title': 'Test Page',
            'description': 'A test page',
            'headings': [(1, 'Heading 1')],
        }
        
        result = build_page_data(
            url='https://example.com/page',
            extracted=extracted,
            depth=1,
        )
        
        self.assertEqual(result['url'], 'https://example.com/page')
        self.assertEqual(result['title'], 'Test Page')
        self.assertEqual(result['description'], 'A test page')
        self.assertEqual(result['text'], 'Page content')
        self.assertEqual(result['headings'], [(1, 'Heading 1')])
        self.assertEqual(result['depth'], 1)
        self.assertIsNotNone(result['crawled_at'])
    
    def test_page_data_with_etag(self):
        """build_page_data should include etag when provided."""
        extracted = {'text': '', 'title': '', 'description': '', 'headings': []}
        
        result = build_page_data(
            url='https://example.com/',
            extracted=extracted,
            depth=0,
            etag='"abc123"',
        )
        
        self.assertEqual(result['etag'], '"abc123"')
    
    def test_page_data_with_last_modified(self):
        """build_page_data should include last_modified when provided."""
        extracted = {'text': '', 'title': '', 'description': '', 'headings': []}
        
        result = build_page_data(
            url='https://example.com/',
            extracted=extracted,
            depth=0,
            last_modified='Wed, 01 Jan 2025 00:00:00 GMT',
        )
        
        self.assertEqual(result['last_modified'], 'Wed, 01 Jan 2025 00:00:00 GMT')
    
    def test_page_data_with_hash(self):
        """build_page_data should include content_hash when provided."""
        extracted = {'text': '', 'title': '', 'description': '', 'headings': []}
        
        result = build_page_data(
            url='https://example.com/',
            extracted=extracted,
            depth=0,
            hash_value='abc123hash',
        )
        
        self.assertEqual(result['content_hash'], 'abc123hash')
    
    def test_page_data_defaults_to_none(self):
        """Optional fields should default to None."""
        extracted = {'text': '', 'title': '', 'description': '', 'headings': []}
        
        result = build_page_data(
            url='https://example.com/',
            extracted=extracted,
            depth=0,
        )
        
        self.assertIsNone(result['etag'])
        self.assertIsNone(result['last_modified'])
        self.assertIsNone(result['content_hash'])
    
    def test_crawled_at_is_recent(self):
        """crawled_at should be a recent timestamp."""
        import time
        
        extracted = {'text': '', 'title': '', 'description': '', 'headings': []}
        
        before = time.time()
        result = build_page_data(
            url='https://example.com/',
            extracted=extracted,
            depth=0,
        )
        after = time.time()
        
        self.assertGreaterEqual(result['crawled_at'], before)
        self.assertLessEqual(result['crawled_at'], after)


class TestBuildDocumentData(unittest.TestCase):
    """Tests for the build_document_data function."""
    
    def test_basic_document_data(self):
        """build_document_data should return a dict with required fields."""
        result = build_document_data(
            url='https://example.com/doc.pdf',
            title='Test Document',
            text='Document content here',
            depth=2,
            doc_type='pdf',
            doc_pages=10,
        )
        
        self.assertEqual(result['url'], 'https://example.com/doc.pdf')
        self.assertEqual(result['title'], 'Test Document')
        self.assertEqual(result['text'], 'Document content here')
        self.assertEqual(result['depth'], 2)
        self.assertEqual(result['doc_type'], 'pdf')
        self.assertEqual(result['doc_pages'], 10)
        self.assertEqual(result['description'], 'PDF document, 10 pages')
        self.assertEqual(result['headings'], [])
        self.assertIsNotNone(result['crawled_at'])
    
    def test_document_data_with_metadata(self):
        """build_document_data should include doc_metadata when provided."""
        metadata = {'author': 'John Doe', 'created': '2025-01-01'}
        
        result = build_document_data(
            url='https://example.com/doc.pdf',
            title='Test',
            text='Content',
            depth=0,
            doc_type='pdf',
            doc_metadata=metadata,
        )
        
        self.assertEqual(result['doc_metadata'], metadata)
    
    def test_document_data_default_metadata(self):
        """doc_metadata should default to empty dict."""
        result = build_document_data(
            url='https://example.com/doc.pdf',
            title='Test',
            text='Content',
            depth=0,
            doc_type='pdf',
        )
        
        self.assertEqual(result['doc_metadata'], {})
    
    def test_document_data_default_pages(self):
        """doc_pages should default to 0."""
        result = build_document_data(
            url='https://example.com/doc.pdf',
            title='Test',
            text='Content',
            depth=0,
            doc_type='pdf',
        )
        
        self.assertEqual(result['doc_pages'], 0)
        self.assertEqual(result['description'], 'PDF document, 0 pages')
    
    def test_document_data_docx_type(self):
        """build_document_data should work for DOCX type."""
        result = build_document_data(
            url='https://example.com/doc.docx',
            title='Word Doc',
            text='Word content',
            depth=1,
            doc_type='docx',
            doc_pages=5,
        )
        
        self.assertEqual(result['doc_type'], 'docx')
        self.assertEqual(result['description'], 'DOCX document, 5 pages')


# ============================================================================
# Test PageProcessor Class
# ============================================================================

class TestPageProcessorInit(unittest.TestCase):
    """Tests for PageProcessor initialization."""
    
    def test_init_creates_directory(self):
        """PageProcessor should create pages_dir if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'new_pages'
            self.assertFalse(pages_dir.exists())
            
            processor = PageProcessor(pages_dir)
            
            self.assertTrue(pages_dir.exists())
            self.assertEqual(processor.pages_dir, pages_dir)
    
    def test_init_uses_existing_directory(self):
        """PageProcessor should work with existing directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            
            processor = PageProcessor(pages_dir)
            
            self.assertEqual(processor.pages_dir, pages_dir)
    
    def test_init_accepts_string_path(self):
        """PageProcessor should accept string paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = str(Path(tmpdir) / 'pages')
            
            processor = PageProcessor(pages_dir)
            
            self.assertEqual(processor.pages_dir, Path(pages_dir))


class TestPageProcessorProcessHtml(unittest.TestCase):
    """Tests for PageProcessor.process_html method."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.pages_dir = Path(self.tmpdir) / 'pages'
        self.processor = PageProcessor(self.pages_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_process_html_returns_dict(self):
        """process_html should return a dict with expected keys."""
        html = '<html><title>Test</title><body>Hello</body></html>'
        
        result = self.processor.process_html(
            url='https://example.com/page',
            html=html,
            depth=0,
        )
        
        self.assertIn('page_data', result)
        self.assertIn('links', result)
        self.assertIn('content_hash', result)
    
    def test_process_html_extracts_title(self):
        """process_html should extract the page title."""
        html = '<html><title>My Page Title</title><body>Content</body></html>'
        
        result = self.processor.process_html(
            url='https://example.com/',
            html=html,
            depth=0,
        )
        
        self.assertEqual(result['page_data']['title'], 'My Page Title')
    
    def test_process_html_extracts_text(self):
        """process_html should extract text content."""
        html = '<html><body><p>Hello World</p></body></html>'
        
        result = self.processor.process_html(
            url='https://example.com/',
            html=html,
            depth=0,
        )
        
        self.assertIn('Hello World', result['page_data']['text'])
    
    def test_process_html_extracts_links(self):
        """process_html should extract links from HTML."""
        html = '''
        <html><body>
            <a href="/page1">Link 1</a>
            <a href="/page2">Link 2</a>
        </body></html>
        '''
        
        result = self.processor.process_html(
            url='https://example.com/',
            html=html,
            depth=0,
        )
        
        links = [url for url, depth in result['links']]
        self.assertIn('https://example.com/page1', links)
        self.assertIn('https://example.com/page2', links)
    
    def test_process_html_increments_link_depth(self):
        """Discovered links should have depth + 1."""
        html = '<html><body><a href="/page">Link</a></body></html>'
        
        result = self.processor.process_html(
            url='https://example.com/',
            html=html,
            depth=2,
        )
        
        for url, depth in result['links']:
            self.assertEqual(depth, 3)
    
    def test_process_html_with_link_filter(self):
        """process_html should apply link filter."""
        html = '''
        <html><body>
            <a href="/allowed">Allowed</a>
            <a href="/blocked">Blocked</a>
        </body></html>
        '''
        
        def link_filter(url, depth):
            return 'allowed' in url
        
        result = self.processor.process_html(
            url='https://example.com/',
            html=html,
            depth=0,
            link_filter=link_filter,
        )
        
        links = [url for url, depth in result['links']]
        self.assertIn('https://example.com/allowed', links)
        self.assertNotIn('https://example.com/blocked', links)
    
    def test_process_html_includes_content_hash(self):
        """process_html should include content hash."""
        html = '<html><body>Test content</body></html>'
        
        result = self.processor.process_html(
            url='https://example.com/',
            html=html,
            depth=0,
        )
        
        self.assertEqual(len(result['content_hash']), 64)
        self.assertEqual(result['page_data']['content_hash'], result['content_hash'])
    
    def test_process_html_includes_incremental_metadata(self):
        """process_html should include etag and last_modified."""
        html = '<html><body>Content</body></html>'
        
        result = self.processor.process_html(
            url='https://example.com/',
            html=html,
            depth=0,
            etag='"abc123"',
            last_modified='Wed, 01 Jan 2025 00:00:00 GMT',
        )
        
        self.assertEqual(result['page_data']['etag'], '"abc123"')
        self.assertEqual(result['page_data']['last_modified'], 'Wed, 01 Jan 2025 00:00:00 GMT')
    
    def test_process_html_uses_base_url_for_links(self):
        """process_html should use base_url for resolving links."""
        html = '<html><body><a href="/page">Link</a></body></html>'
        
        result = self.processor.process_html(
            url='https://example.com/current',
            html=html,
            depth=0,
            base_url='https://other.com/',
        )
        
        links = [url for url, depth in result['links']]
        self.assertIn('https://other.com/page', links)


class TestPageProcessorIsContentChanged(unittest.TestCase):
    """Tests for PageProcessor.is_content_changed method."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.processor = PageProcessor(Path(self.tmpdir) / 'pages')
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_content_changed_when_no_existing_metadata(self):
        """Content should be considered changed when no existing metadata."""
        changed, hash_val = self.processor.is_content_changed(
            html='<html>Content</html>',
            existing_metadata=None,
        )
        
        self.assertTrue(changed)
        self.assertEqual(len(hash_val), 64)
    
    def test_content_changed_when_no_existing_hash(self):
        """Content should be considered changed when existing metadata has no hash."""
        changed, hash_val = self.processor.is_content_changed(
            html='<html>Content</html>',
            existing_metadata={'url': 'https://example.com'},
        )
        
        self.assertTrue(changed)
    
    def test_content_unchanged_when_hash_matches(self):
        """Content should be unchanged when hash matches."""
        html = '<html>Same content</html>'
        hash_val = content_hash(html)
        
        changed, new_hash = self.processor.is_content_changed(
            html=html,
            existing_metadata={'content_hash': hash_val},
        )
        
        self.assertFalse(changed)
        self.assertEqual(new_hash, hash_val)
    
    def test_content_changed_when_hash_differs(self):
        """Content should be changed when hash differs."""
        changed, hash_val = self.processor.is_content_changed(
            html='<html>New content</html>',
            existing_metadata={'content_hash': 'old_hash_value'},
        )
        
        self.assertTrue(changed)


class TestPageProcessorPersistence(unittest.TestCase):
    """Tests for PageProcessor save/load methods."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.pages_dir = Path(self.tmpdir) / 'pages'
        self.processor = PageProcessor(self.pages_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_save_page_creates_file(self):
        """save_page should create a JSON file."""
        url = 'https://example.com/page'
        data = {'url': url, 'title': 'Test', 'text': 'Content'}
        
        filepath = self.processor.save_page(url, data)
        
        self.assertTrue(filepath.exists())
        self.assertTrue(filepath.suffix == '.json')
    
    def test_save_and_load_roundtrip(self):
        """Data should survive save/load roundtrip."""
        url = 'https://example.com/page'
        data = {
            'url': url,
            'title': 'Test Page',
            'text': 'Page content',
            'headings': [(1, 'Heading')],
            'depth': 2,
        }
        
        self.processor.save_page(url, data)
        loaded = self.processor.load_page_metadata(url)
        
        self.assertEqual(loaded['url'], data['url'])
        self.assertEqual(loaded['title'], data['title'])
        self.assertEqual(loaded['text'], data['text'])
        self.assertEqual(loaded['depth'], data['depth'])
    
    def test_load_nonexistent_page_returns_none(self):
        """load_page_metadata should return None for nonexistent pages."""
        result = self.processor.load_page_metadata('https://example.com/nonexistent')
        
        self.assertIsNone(result)
    
    def test_load_corrupted_file_returns_none(self):
        """load_page_metadata should return None for corrupted files."""
        from doc_search.utils import url_to_filename
        
        url = 'https://example.com/corrupted'
        filename = url_to_filename(url) + '.json'
        filepath = self.pages_dir / filename
        
        # Write invalid JSON
        with open(filepath, 'w') as f:
            f.write('not valid json{{{')
        
        result = self.processor.load_page_metadata(url)
        
        self.assertIsNone(result)
    
    def test_page_exists_returns_true_for_saved_page(self):
        """page_exists should return True for saved pages."""
        url = 'https://example.com/page'
        self.processor.save_page(url, {'url': url})
        
        self.assertTrue(self.processor.page_exists(url))
    
    def test_page_exists_returns_false_for_unsaved_page(self):
        """page_exists should return False for unsaved pages."""
        self.assertFalse(self.processor.page_exists('https://example.com/unsaved'))


class TestPageProcessorIterSavedPages(unittest.TestCase):
    """Tests for PageProcessor.iter_saved_pages method."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.pages_dir = Path(self.tmpdir) / 'pages'
        self.processor = PageProcessor(self.pages_dir)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_iter_empty_directory(self):
        """iter_saved_pages should yield nothing for empty directory."""
        pages = list(self.processor.iter_saved_pages())
        self.assertEqual(len(pages), 0)
    
    def test_iter_yields_all_pages(self):
        """iter_saved_pages should yield all saved pages."""
        urls = [
            'https://example.com/page1',
            'https://example.com/page2',
            'https://example.com/page3',
        ]
        
        for url in urls:
            self.processor.save_page(url, {'url': url})
        
        pages = list(self.processor.iter_saved_pages())
        page_urls = {p['url'] for p in pages}
        
        self.assertEqual(len(pages), 3)
        for url in urls:
            self.assertIn(url, page_urls)
    
    def test_iter_skips_corrupted_files(self):
        """iter_saved_pages should skip corrupted files."""
        from doc_search.utils import url_to_filename
        
        # Save valid page
        self.processor.save_page('https://example.com/valid', {'url': 'valid'})
        
        # Create corrupted file
        corrupted_path = self.pages_dir / 'corrupted.json'
        with open(corrupted_path, 'w') as f:
            f.write('invalid json')
        
        pages = list(self.processor.iter_saved_pages(warn_on_error=False))
        
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]['url'], 'valid')
    
    def test_iter_warns_on_corrupted_files(self):
        """iter_saved_pages should warn about corrupted files when warn_on_error=True."""
        # Create corrupted file
        corrupted_path = self.pages_dir / 'corrupted.json'
        with open(corrupted_path, 'w') as f:
            f.write('invalid json')
        
        with patch('builtins.print') as mock_print:
            list(self.processor.iter_saved_pages(warn_on_error=True))
            mock_print.assert_called()
            call_arg = str(mock_print.call_args)
            self.assertIn('Warning', call_arg)


# ============================================================================
# Test Module Exports
# ============================================================================

class TestModuleExports(unittest.TestCase):
    """Tests for module exports."""
    
    def test_can_import_from_processor(self):
        """All public items should be importable from processor."""
        from doc_search.crawler.processor import (
            PageProcessor,
            content_hash,
            build_page_data,
            build_document_data,
        )
        
        self.assertIsNotNone(PageProcessor)
        self.assertIsNotNone(content_hash)
        self.assertIsNotNone(build_page_data)
        self.assertIsNotNone(build_document_data)
    
    def test_can_import_from_crawler_package(self):
        """All public items should be importable from crawler package."""
        from doc_search.crawler import (
            PageProcessor,
            content_hash,
            build_page_data,
            build_document_data,
        )
        
        self.assertIsNotNone(PageProcessor)
        self.assertIsNotNone(content_hash)
        self.assertIsNotNone(build_page_data)
        self.assertIsNotNone(build_document_data)


if __name__ == '__main__':
    unittest.main()
