"""
Tests for the URL filtering module.
"""

import unittest
from unittest.mock import Mock, patch

from doc_search.crawler.url_filter import (
    SKIP_EXTENSIONS,
    EXTRACTABLE_DOC_EXTENSIONS,
    SKIP_PATH_PATTERNS,
    is_skippable_extension,
    is_extractable_doc,
    is_skippable_path,
    is_under_base_path,
    UrlFilter,
)


# ============================================================================
# Test Constants
# ============================================================================

class TestConstants(unittest.TestCase):
    """Test the module-level constants."""
    
    def test_skip_extensions_is_frozenset(self):
        """SKIP_EXTENSIONS should be a frozenset for immutability."""
        self.assertIsInstance(SKIP_EXTENSIONS, frozenset)
    
    def test_skip_extensions_contains_common_binaries(self):
        """SKIP_EXTENSIONS should contain common binary extensions."""
        # Archives
        self.assertIn('.zip', SKIP_EXTENSIONS)
        self.assertIn('.tar', SKIP_EXTENSIONS)
        self.assertIn('.gz', SKIP_EXTENSIONS)
        self.assertIn('.rar', SKIP_EXTENSIONS)
        self.assertIn('.7z', SKIP_EXTENSIONS)
        
        # Images
        self.assertIn('.jpg', SKIP_EXTENSIONS)
        self.assertIn('.png', SKIP_EXTENSIONS)
        self.assertIn('.gif', SKIP_EXTENSIONS)
        self.assertIn('.svg', SKIP_EXTENSIONS)
        
        # Media
        self.assertIn('.mp3', SKIP_EXTENSIONS)
        self.assertIn('.mp4', SKIP_EXTENSIONS)
        self.assertIn('.avi', SKIP_EXTENSIONS)
        
        # Executables
        self.assertIn('.exe', SKIP_EXTENSIONS)
        self.assertIn('.dmg', SKIP_EXTENSIONS)
        self.assertIn('.deb', SKIP_EXTENSIONS)
        
        # Code/data files
        self.assertIn('.css', SKIP_EXTENSIONS)
        self.assertIn('.js', SKIP_EXTENSIONS)
        self.assertIn('.json', SKIP_EXTENSIONS)
    
    def test_extractable_doc_extensions_is_frozenset(self):
        """EXTRACTABLE_DOC_EXTENSIONS should be a frozenset."""
        self.assertIsInstance(EXTRACTABLE_DOC_EXTENSIONS, frozenset)
    
    def test_extractable_doc_extensions_contains_documents(self):
        """EXTRACTABLE_DOC_EXTENSIONS should contain document extensions."""
        self.assertIn('.pdf', EXTRACTABLE_DOC_EXTENSIONS)
        self.assertIn('.doc', EXTRACTABLE_DOC_EXTENSIONS)
        self.assertIn('.docx', EXTRACTABLE_DOC_EXTENSIONS)
        self.assertIn('.xls', EXTRACTABLE_DOC_EXTENSIONS)
        self.assertIn('.xlsx', EXTRACTABLE_DOC_EXTENSIONS)
    
    def test_skip_path_patterns_is_list(self):
        """SKIP_PATH_PATTERNS should be a list."""
        self.assertIsInstance(SKIP_PATH_PATTERNS, list)
    
    def test_skip_path_patterns_contains_common_patterns(self):
        """SKIP_PATH_PATTERNS should contain common non-doc patterns."""
        self.assertIn('/download/', SKIP_PATH_PATTERNS)
        self.assertIn('/downloads/', SKIP_PATH_PATTERNS)
        self.assertIn('/archive/', SKIP_PATH_PATTERNS)
        self.assertIn('/releases/', SKIP_PATH_PATTERNS)
        self.assertIn('/dist/', SKIP_PATH_PATTERNS)


# ============================================================================
# Test Standalone Functions
# ============================================================================

class TestIsSkippableExtension(unittest.TestCase):
    """Tests for the is_skippable_extension function."""
    
    def test_skippable_archive_extensions(self):
        """Archive extensions should be skipped."""
        self.assertTrue(is_skippable_extension('https://example.com/file.zip'))
        self.assertTrue(is_skippable_extension('https://example.com/file.tar'))
        self.assertTrue(is_skippable_extension('https://example.com/file.gz'))
        self.assertTrue(is_skippable_extension('https://example.com/file.tar.gz'))
        self.assertTrue(is_skippable_extension('https://example.com/file.tar.bz2'))
        self.assertTrue(is_skippable_extension('https://example.com/file.7z'))
    
    def test_skippable_image_extensions(self):
        """Image extensions should be skipped."""
        self.assertTrue(is_skippable_extension('https://example.com/image.jpg'))
        self.assertTrue(is_skippable_extension('https://example.com/image.jpeg'))
        self.assertTrue(is_skippable_extension('https://example.com/image.png'))
        self.assertTrue(is_skippable_extension('https://example.com/image.gif'))
        self.assertTrue(is_skippable_extension('https://example.com/image.svg'))
        self.assertTrue(is_skippable_extension('https://example.com/icon.ico'))
    
    def test_skippable_media_extensions(self):
        """Media extensions should be skipped."""
        self.assertTrue(is_skippable_extension('https://example.com/video.mp4'))
        self.assertTrue(is_skippable_extension('https://example.com/audio.mp3'))
        self.assertTrue(is_skippable_extension('https://example.com/video.avi'))
        self.assertTrue(is_skippable_extension('https://example.com/video.mkv'))
    
    def test_skippable_code_data_extensions(self):
        """Code and data file extensions should be skipped."""
        self.assertTrue(is_skippable_extension('https://example.com/style.css'))
        self.assertTrue(is_skippable_extension('https://example.com/script.js'))
        self.assertTrue(is_skippable_extension('https://example.com/data.json'))
        self.assertTrue(is_skippable_extension('https://example.com/font.woff2'))
    
    def test_compound_extensions_tar_gz(self):
        """Compound extensions like .tar.gz should be skipped."""
        self.assertTrue(is_skippable_extension('https://example.com/archive.tar.gz'))
        self.assertTrue(is_skippable_extension('https://example.com/file.tar.bz2'))
        self.assertTrue(is_skippable_extension('https://example.com/file.tar.xz'))
    
    def test_html_not_skipped(self):
        """HTML extensions should not be skipped."""
        self.assertFalse(is_skippable_extension('https://example.com/page.html'))
        self.assertFalse(is_skippable_extension('https://example.com/page.htm'))
    
    def test_no_extension_not_skipped(self):
        """URLs without extensions should not be skipped."""
        self.assertFalse(is_skippable_extension('https://example.com/page'))
        self.assertFalse(is_skippable_extension('https://example.com/docs/'))
        self.assertFalse(is_skippable_extension('https://example.com/'))
    
    def test_case_insensitive(self):
        """Extension checking should be case-insensitive."""
        self.assertTrue(is_skippable_extension('https://example.com/file.ZIP'))
        self.assertTrue(is_skippable_extension('https://example.com/image.PNG'))
        self.assertTrue(is_skippable_extension('https://example.com/IMAGE.JPG'))
    
    def test_pdf_skipped_without_extract_docs(self):
        """PDF should be skipped when extract_docs=False."""
        self.assertTrue(is_skippable_extension('https://example.com/doc.pdf'))
        self.assertTrue(is_skippable_extension('https://example.com/file.docx'))
        self.assertTrue(is_skippable_extension('https://example.com/data.xlsx'))
    
    def test_pdf_not_skipped_with_extract_docs(self):
        """PDF should not be skipped when extract_docs=True."""
        self.assertFalse(is_skippable_extension('https://example.com/doc.pdf', extract_docs=True))
        self.assertFalse(is_skippable_extension('https://example.com/file.docx', extract_docs=True))
        self.assertFalse(is_skippable_extension('https://example.com/data.xlsx', extract_docs=True))


class TestIsExtractableDoc(unittest.TestCase):
    """Tests for the is_extractable_doc function."""
    
    def test_pdf_is_extractable(self):
        """PDF files should be extractable."""
        self.assertTrue(is_extractable_doc('https://example.com/document.pdf'))
        self.assertTrue(is_extractable_doc('https://example.com/path/to/file.pdf'))
    
    def test_office_docs_are_extractable(self):
        """Office document files should be extractable."""
        self.assertTrue(is_extractable_doc('https://example.com/doc.doc'))
        self.assertTrue(is_extractable_doc('https://example.com/doc.docx'))
        self.assertTrue(is_extractable_doc('https://example.com/spreadsheet.xls'))
        self.assertTrue(is_extractable_doc('https://example.com/spreadsheet.xlsx'))
    
    def test_html_not_extractable(self):
        """HTML files should not be considered extractable docs."""
        self.assertFalse(is_extractable_doc('https://example.com/page.html'))
    
    def test_zip_not_extractable(self):
        """Archives should not be considered extractable docs."""
        self.assertFalse(is_extractable_doc('https://example.com/file.zip'))
    
    def test_no_extension_not_extractable(self):
        """URLs without extensions should not be extractable."""
        self.assertFalse(is_extractable_doc('https://example.com/page'))
    
    def test_case_insensitive(self):
        """Extension checking should be case-insensitive."""
        self.assertTrue(is_extractable_doc('https://example.com/doc.PDF'))
        self.assertTrue(is_extractable_doc('https://example.com/doc.DOCX'))


class TestIsSkippablePath(unittest.TestCase):
    """Tests for the is_skippable_path function."""
    
    def test_download_paths_skipped(self):
        """Download paths should be skipped."""
        self.assertTrue(is_skippable_path('https://example.com/download/file'))
        self.assertTrue(is_skippable_path('https://example.com/downloads/file'))
    
    def test_archive_paths_skipped(self):
        """Archive paths should be skipped."""
        self.assertTrue(is_skippable_path('https://example.com/archive/2023'))
        self.assertTrue(is_skippable_path('https://example.com/archives/old'))
    
    def test_release_paths_skipped(self):
        """Release paths should be skipped."""
        self.assertTrue(is_skippable_path('https://example.com/releases/v1.0'))
        self.assertTrue(is_skippable_path('https://example.com/release/latest'))
    
    def test_dist_paths_skipped(self):
        """Distribution paths should be skipped."""
        self.assertTrue(is_skippable_path('https://example.com/dist/package'))
        self.assertTrue(is_skippable_path('https://example.com/ftp/files'))
    
    def test_source_paths_skipped(self):
        """Source paths should be skipped."""
        self.assertTrue(is_skippable_path('https://example.com/source/code'))
        self.assertTrue(is_skippable_path('https://example.com/sources/lib'))
    
    def test_package_paths_skipped(self):
        """Package paths should be skipped."""
        self.assertTrue(is_skippable_path('https://example.com/packages/npm'))
        self.assertTrue(is_skippable_path('https://example.com/pkg/latest'))
    
    def test_binary_paths_skipped(self):
        """Binary paths should be skipped."""
        self.assertTrue(is_skippable_path('https://example.com/binaries/x64'))
        self.assertTrue(is_skippable_path('https://example.com/bin/exec'))
    
    def test_docs_paths_not_skipped(self):
        """Documentation paths should not be skipped."""
        self.assertFalse(is_skippable_path('https://example.com/docs/guide'))
        self.assertFalse(is_skippable_path('https://example.com/documentation/api'))
    
    def test_api_paths_not_skipped(self):
        """API documentation paths should not be skipped."""
        self.assertFalse(is_skippable_path('https://example.com/api/reference'))
    
    def test_root_path_not_skipped(self):
        """Root path should not be skipped."""
        self.assertFalse(is_skippable_path('https://example.com/'))
    
    def test_case_insensitive(self):
        """Path checking should be case-insensitive."""
        self.assertTrue(is_skippable_path('https://example.com/DOWNLOAD/file'))
        self.assertTrue(is_skippable_path('https://example.com/Downloads/file'))


class TestIsUnderBasePath(unittest.TestCase):
    """Tests for the is_under_base_path function."""
    
    def test_exact_match(self):
        """URL path that exactly matches base_path should be under it."""
        self.assertTrue(is_under_base_path(
            'https://example.com/docs',
            '/docs',
            same_path=True
        ))
    
    def test_subpath_match(self):
        """URL path under base_path should be under it."""
        self.assertTrue(is_under_base_path(
            'https://example.com/docs/guide',
            '/docs',
            same_path=True
        ))
        self.assertTrue(is_under_base_path(
            'https://example.com/docs/api/reference',
            '/docs',
            same_path=True
        ))
    
    def test_different_path_not_under(self):
        """URL path not under base_path should not be under it."""
        self.assertFalse(is_under_base_path(
            'https://example.com/other',
            '/docs',
            same_path=True
        ))
        self.assertFalse(is_under_base_path(
            'https://example.com/documentation',
            '/docs',
            same_path=True
        ))
    
    def test_sibling_path_not_under(self):
        """Sibling paths should not be considered under base_path."""
        # /docs-extra is NOT under /docs
        self.assertFalse(is_under_base_path(
            'https://example.com/docs-extra',
            '/docs',
            same_path=True
        ))
    
    def test_same_path_false_returns_true(self):
        """When same_path=False, should always return True."""
        self.assertTrue(is_under_base_path(
            'https://example.com/other',
            '/docs',
            same_path=False
        ))
    
    def test_empty_base_path_returns_true(self):
        """Empty base_path should always return True."""
        self.assertTrue(is_under_base_path(
            'https://example.com/anything',
            '',
            same_path=True
        ))
    
    def test_trailing_slash_handling(self):
        """Should handle trailing slashes correctly."""
        # URL with trailing slash
        self.assertTrue(is_under_base_path(
            'https://example.com/docs/',
            '/docs',
            same_path=True
        ))
        # Deeply nested with trailing slash
        self.assertTrue(is_under_base_path(
            'https://example.com/docs/guide/',
            '/docs',
            same_path=True
        ))
    
    def test_version_paths(self):
        """Should work with version paths like /3.11."""
        self.assertTrue(is_under_base_path(
            'https://docs.python.org/3.11',
            '/3.11',
            same_path=True
        ))
        self.assertTrue(is_under_base_path(
            'https://docs.python.org/3.11/library/os.html',
            '/3.11',
            same_path=True
        ))
        # Should not match /3.11x or /3.111
        self.assertFalse(is_under_base_path(
            'https://docs.python.org/3.111',
            '/3.11',
            same_path=True
        ))


# ============================================================================
# Test UrlFilter Class
# ============================================================================

class TestUrlFilterInit(unittest.TestCase):
    """Tests for UrlFilter initialization."""
    
    def test_basic_init(self):
        """Test basic initialization."""
        url_filter = UrlFilter('https://example.com/docs/')
        
        self.assertEqual(url_filter.base_url, 'https://example.com/docs/')
        self.assertEqual(url_filter.base_domain, 'example.com')
        self.assertEqual(url_filter.base_path, '/docs')
        self.assertTrue(url_filter.stay_on_domain)
        self.assertFalse(url_filter.same_path)  # default
        self.assertFalse(url_filter.extract_docs)
        self.assertIsNone(url_filter.max_depth)
        self.assertIsNone(url_filter.custom_filter)
    
    def test_init_with_same_path(self):
        """Test initialization with same_path=True."""
        url_filter = UrlFilter('https://example.com/docs/', same_path=True)
        
        self.assertTrue(url_filter.same_path)
        self.assertEqual(url_filter.base_path, '/docs')
    
    def test_root_path_disables_same_path(self):
        """Root paths should disable same_path restriction."""
        url_filter = UrlFilter('https://example.com/', same_path=True)
        
        # same_path should be disabled for root
        self.assertFalse(url_filter.same_path)
        self.assertEqual(url_filter.base_path, '')
    
    def test_init_with_robots_checker(self):
        """Test initialization with robots checker."""
        mock_robots = Mock()
        url_filter = UrlFilter('https://example.com/', robots_checker=mock_robots)
        
        self.assertEqual(url_filter.robots_checker, mock_robots)
    
    def test_init_with_custom_filter(self):
        """Test initialization with custom filter function."""
        custom_fn = lambda url: 'allowed' in url
        url_filter = UrlFilter('https://example.com/', url_filter=custom_fn)
        
        self.assertEqual(url_filter.custom_filter, custom_fn)


class TestUrlFilterMethods(unittest.TestCase):
    """Tests for UrlFilter instance methods."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.url_filter = UrlFilter(
            'https://example.com/docs/',
            same_path=True,
            extract_docs=False,
        )
    
    def test_is_skippable_extension_delegates(self):
        """is_skippable_extension should delegate to module function."""
        self.assertTrue(self.url_filter.is_skippable_extension('https://example.com/file.zip'))
        self.assertFalse(self.url_filter.is_skippable_extension('https://example.com/page.html'))
    
    def test_is_skippable_extension_respects_extract_docs(self):
        """is_skippable_extension should respect extract_docs setting."""
        # Default (extract_docs=False) - PDF is skipped
        self.assertTrue(self.url_filter.is_skippable_extension('https://example.com/doc.pdf'))
        
        # With extract_docs=True - PDF is not skipped
        url_filter_docs = UrlFilter('https://example.com/', extract_docs=True)
        self.assertFalse(url_filter_docs.is_skippable_extension('https://example.com/doc.pdf'))
    
    def test_is_extractable_doc_delegates(self):
        """is_extractable_doc should delegate to module function."""
        self.assertTrue(self.url_filter.is_extractable_doc('https://example.com/doc.pdf'))
        self.assertFalse(self.url_filter.is_extractable_doc('https://example.com/page.html'))
    
    def test_is_skippable_path_delegates(self):
        """is_skippable_path should delegate to module function."""
        self.assertTrue(self.url_filter.is_skippable_path('https://example.com/download/file'))
        self.assertFalse(self.url_filter.is_skippable_path('https://example.com/docs/guide'))
    
    def test_is_under_base_path_delegates(self):
        """is_under_base_path should delegate to module function."""
        self.assertTrue(self.url_filter.is_under_base_path('https://example.com/docs/guide'))
        self.assertFalse(self.url_filter.is_under_base_path('https://example.com/other'))


class TestUrlFilterShouldFollow(unittest.TestCase):
    """Tests for UrlFilter.should_follow method."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_robots = Mock()
        self.mock_robots.can_fetch.return_value = True
        
        self.url_filter = UrlFilter(
            'https://example.com/docs/',
            robots_checker=self.mock_robots,
            stay_on_domain=True,
            same_path=True,
            extract_docs=False,
            max_depth=3,
        )
    
    def test_should_follow_valid_url(self):
        """Valid URL should be followed."""
        self.assertTrue(self.url_filter.should_follow(
            'https://example.com/docs/guide',
            depth=1
        ))
    
    def test_should_not_follow_visited_url(self):
        """Already visited URL should not be followed."""
        is_visited = lambda url: url == 'https://example.com/docs/visited'
        
        self.assertFalse(self.url_filter.should_follow(
            'https://example.com/docs/visited',
            depth=1,
            is_visited_func=is_visited
        ))
    
    def test_should_follow_visited_url_with_force(self):
        """Visited URL should be followed when force=True."""
        is_visited = lambda url: url == 'https://example.com/docs/visited'
        
        self.assertTrue(self.url_filter.should_follow(
            'https://example.com/docs/visited',
            depth=1,
            is_visited_func=is_visited,
            force=True
        ))
    
    def test_should_not_follow_beyond_max_depth(self):
        """URL beyond max_depth should not be followed."""
        self.assertFalse(self.url_filter.should_follow(
            'https://example.com/docs/guide',
            depth=4  # max_depth=3
        ))
    
    def test_should_not_follow_skippable_extension(self):
        """URL with skippable extension should not be followed."""
        self.assertFalse(self.url_filter.should_follow(
            'https://example.com/docs/image.png',
            depth=1
        ))
    
    def test_should_not_follow_skippable_path(self):
        """URL with skippable path should not be followed."""
        self.assertFalse(self.url_filter.should_follow(
            'https://example.com/docs/download/file',
            depth=1
        ))
    
    def test_should_not_follow_different_domain(self):
        """URL on different domain should not be followed."""
        self.assertFalse(self.url_filter.should_follow(
            'https://other.com/docs/guide',
            depth=1
        ))
    
    def test_should_not_follow_outside_base_path(self):
        """URL outside base_path should not be followed."""
        self.assertFalse(self.url_filter.should_follow(
            'https://example.com/other/page',
            depth=1
        ))
    
    def test_should_not_follow_robots_disallowed(self):
        """URL disallowed by robots.txt should not be followed."""
        self.mock_robots.can_fetch.return_value = False
        
        self.assertFalse(self.url_filter.should_follow(
            'https://example.com/docs/private',
            depth=1
        ))
    
    def test_should_not_follow_custom_filter_reject(self):
        """URL rejected by custom filter should not be followed."""
        url_filter = UrlFilter(
            'https://example.com/',
            url_filter=lambda url: 'allowed' in url
        )
        
        self.assertFalse(url_filter.should_follow(
            'https://example.com/rejected',
            depth=1
        ))
        self.assertTrue(url_filter.should_follow(
            'https://example.com/allowed-page',
            depth=1
        ))
    
    def test_should_follow_without_robots_checker(self):
        """URL should be followed even without robots checker."""
        url_filter = UrlFilter('https://example.com/', robots_checker=None)
        
        self.assertTrue(url_filter.should_follow(
            'https://example.com/page',
            depth=1
        ))
    
    def test_should_follow_without_is_visited_func(self):
        """URL should be followed without is_visited_func."""
        self.assertTrue(self.url_filter.should_follow(
            'https://example.com/docs/guide',
            depth=1,
            is_visited_func=None
        ))
    
    def test_should_follow_no_max_depth(self):
        """URL at any depth should be followed when max_depth is None."""
        url_filter = UrlFilter('https://example.com/', max_depth=None)
        
        self.assertTrue(url_filter.should_follow(
            'https://example.com/deep/nested/path',
            depth=100
        ))
    
    def test_cross_domain_allowed_when_stay_on_domain_false(self):
        """Cross-domain URLs should be followed when stay_on_domain=False."""
        url_filter = UrlFilter('https://example.com/', stay_on_domain=False)
        
        self.assertTrue(url_filter.should_follow(
            'https://other-domain.com/page',
            depth=1
        ))


class TestUrlFilterEdgeCases(unittest.TestCase):
    """Tests for edge cases in UrlFilter."""
    
    def test_url_with_query_params(self):
        """URLs with query parameters should be handled correctly."""
        url_filter = UrlFilter('https://example.com/docs/')
        
        self.assertTrue(url_filter.should_follow(
            'https://example.com/docs/page?param=value',
            depth=1
        ))
    
    def test_url_with_fragment(self):
        """URLs with fragments should be handled correctly."""
        url_filter = UrlFilter('https://example.com/docs/')
        
        self.assertTrue(url_filter.should_follow(
            'https://example.com/docs/page#section',
            depth=1
        ))
    
    def test_url_with_port(self):
        """URLs with ports should be handled correctly."""
        url_filter = UrlFilter('https://example.com:8080/docs/')
        
        self.assertTrue(url_filter.should_follow(
            'https://example.com:8080/docs/page',
            depth=1
        ))
    
    def test_url_with_username_password(self):
        """URLs with credentials may fail domain matching."""
        url_filter = UrlFilter('https://example.com/docs/')
        
        # URLs with credentials may not match same_domain check
        # This is actually expected behavior - the netloc includes credentials
        # so 'user:pass@example.com' != 'example.com'
        # This test documents the current behavior
        result = url_filter.should_follow(
            'https://user:pass@example.com/docs/page',
            depth=1
        )
        # The URL fails domain check because netloc includes credentials
        self.assertFalse(result)
    
    def test_empty_url(self):
        """Empty URL should be handled gracefully."""
        url_filter = UrlFilter('https://example.com/')
        
        # Empty URL has no domain, so it shouldn't match
        self.assertFalse(url_filter.should_follow('', depth=1))
    
    def test_relative_url_handling(self):
        """Relative URLs should be handled (though typically resolved before filtering)."""
        url_filter = UrlFilter('https://example.com/')
        
        # Relative URLs without domain won't match same_domain check
        self.assertFalse(url_filter.should_follow('/relative/path', depth=1))
    
    def test_extract_docs_pdf_allowed(self):
        """PDF should be allowed when extract_docs=True."""
        url_filter = UrlFilter('https://example.com/', extract_docs=True)
        
        self.assertTrue(url_filter.should_follow(
            'https://example.com/document.pdf',
            depth=1
        ))
    
    def test_always_skip_images_even_with_extract_docs(self):
        """Images should always be skipped even with extract_docs=True."""
        url_filter = UrlFilter('https://example.com/', extract_docs=True)
        
        self.assertFalse(url_filter.should_follow(
            'https://example.com/image.png',
            depth=1
        ))


# ============================================================================
# Test Module Exports
# ============================================================================

class TestModuleExports(unittest.TestCase):
    """Tests for module exports."""
    
    def test_can_import_from_url_filter(self):
        """All public items should be importable from url_filter."""
        from doc_search.crawler.url_filter import (
            SKIP_EXTENSIONS,
            EXTRACTABLE_DOC_EXTENSIONS,
            SKIP_PATH_PATTERNS,
            is_skippable_extension,
            is_extractable_doc,
            is_skippable_path,
            is_under_base_path,
            UrlFilter,
        )
        
        # Just verify they exist
        self.assertIsNotNone(SKIP_EXTENSIONS)
        self.assertIsNotNone(EXTRACTABLE_DOC_EXTENSIONS)
        self.assertIsNotNone(SKIP_PATH_PATTERNS)
        self.assertIsNotNone(is_skippable_extension)
        self.assertIsNotNone(is_extractable_doc)
        self.assertIsNotNone(is_skippable_path)
        self.assertIsNotNone(is_under_base_path)
        self.assertIsNotNone(UrlFilter)
    
    def test_can_import_from_crawler_package(self):
        """All public items should be importable from crawler package."""
        from doc_search.crawler import (
            SKIP_EXTENSIONS,
            EXTRACTABLE_DOC_EXTENSIONS,
            SKIP_PATH_PATTERNS,
            UrlFilter,
            is_skippable_extension,
            is_extractable_doc,
            is_skippable_path,
            is_under_base_path,
        )
        
        # Just verify they exist
        self.assertIsNotNone(SKIP_EXTENSIONS)
        self.assertIsNotNone(UrlFilter)


if __name__ == '__main__':
    unittest.main()
