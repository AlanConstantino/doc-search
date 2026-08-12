"""Tests for BM25Index class."""

import unittest
from doc_search.indexer import BM25Index


class TestBM25IndexParameters(unittest.TestCase):
    """Tests for BM25 parameter validation."""
    
    def test_default_parameters(self):
        """Default parameters should work."""
        index = BM25Index()
        self.assertEqual(index.k1, 1.5)
        self.assertEqual(index.b, 0.75)
        self.assertTrue(index.stem)
    
    def test_custom_valid_parameters(self):
        """Custom valid parameters should work."""
        index = BM25Index(k1=2.0, b=0.5, stem=False)
        self.assertEqual(index.k1, 2.0)
        self.assertEqual(index.b, 0.5)
        self.assertFalse(index.stem)
    
    def test_k1_zero_allowed(self):
        """k1=0 should be allowed."""
        index = BM25Index(k1=0)
        self.assertEqual(index.k1, 0)
    
    def test_k1_negative_rejected(self):
        """Negative k1 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            BM25Index(k1=-0.5)
        self.assertIn('k1', str(ctx.exception))
    
    def test_b_zero_allowed(self):
        """b=0 should be allowed (no length normalization)."""
        index = BM25Index(b=0)
        self.assertEqual(index.b, 0)
    
    def test_b_one_allowed(self):
        """b=1 should be allowed (full length normalization)."""
        index = BM25Index(b=1)
        self.assertEqual(index.b, 1)
    
    def test_b_negative_rejected(self):
        """Negative b should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            BM25Index(b=-0.1)
        self.assertIn('b', str(ctx.exception))
    
    def test_b_greater_than_one_rejected(self):
        """b > 1 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            BM25Index(b=1.5)
        self.assertIn('b', str(ctx.exception))


class TestBM25IndexAccessors(unittest.TestCase):
    """Tests for BM25Index accessor methods."""
    
    def setUp(self):
        """Set up a test index with sample documents."""
        self.index = BM25Index()
        
        # Add sample documents
        self.index.add_document(
            doc_id=0,
            url='https://example.com/page1',
            title='First Page',
            text='This is the first page content.',
            description='Description of first page'
        )
        self.index.add_document(
            doc_id=1,
            url='https://example.com/page2',
            title='Second Page',
            text='This is the second page content.',
            description='Description of second page'
        )
    
    def test_get_doc_id_existing(self):
        """get_doc_id should return correct ID for existing URL."""
        doc_id = self.index.get_doc_id('https://example.com/page1')
        self.assertEqual(doc_id, 0)
        
        doc_id = self.index.get_doc_id('https://example.com/page2')
        self.assertEqual(doc_id, 1)
    
    def test_get_doc_id_nonexistent(self):
        """get_doc_id should return None for non-existent URL."""
        doc_id = self.index.get_doc_id('https://example.com/nonexistent')
        self.assertIsNone(doc_id)
    
    def test_get_document_existing(self):
        """get_document should return document metadata for existing ID."""
        doc = self.index.get_document(0)
        self.assertIsNotNone(doc)
        self.assertEqual(doc['url'], 'https://example.com/page1')
        self.assertEqual(doc['title'], 'First Page')
        self.assertEqual(doc['description'], 'Description of first page')
    
    def test_get_document_nonexistent(self):
        """get_document should return None for non-existent ID."""
        doc = self.index.get_document(999)
        self.assertIsNone(doc)
    
    def test_has_url_existing(self):
        """has_url should return True for indexed URLs."""
        self.assertTrue(self.index.has_url('https://example.com/page1'))
        self.assertTrue(self.index.has_url('https://example.com/page2'))
    
    def test_has_url_nonexistent(self):
        """has_url should return False for non-indexed URLs."""
        self.assertFalse(self.index.has_url('https://example.com/nonexistent'))
        self.assertFalse(self.index.has_url('https://other.com/page'))
    
    def test_accessor_chain(self):
        """Test get_doc_id -> get_document chain."""
        url = 'https://example.com/page2'
        doc_id = self.index.get_doc_id(url)
        self.assertIsNotNone(doc_id)
        
        doc = self.index.get_document(doc_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc['url'], url)


class TestBM25IndexEmpty(unittest.TestCase):
    """Tests for BM25Index accessors with empty index."""
    
    def setUp(self):
        """Set up an empty index."""
        self.index = BM25Index()
    
    def test_get_doc_id_empty(self):
        """get_doc_id should return None for empty index."""
        self.assertIsNone(self.index.get_doc_id('https://any.url'))
    
    def test_get_document_empty(self):
        """get_document should return None for empty index."""
        self.assertIsNone(self.index.get_document(0))
    
    def test_has_url_empty(self):
        """has_url should return False for empty index."""
        self.assertFalse(self.index.has_url('https://any.url'))


class TestBM25IndexNumericSearch(unittest.TestCase):
    """Tests for numeric token indexing and search."""

    def test_numeric_terms_are_searchable(self):
        """Numbers in content should be indexed and searchable."""
        index = BM25Index()
        index.add_document(
            doc_id=0,
            url='https://example.com/release-notes',
            title='Release 2024 Notes',
            text='This release was published in 2024 and supersedes 2023.',
            description='Annual release notes'
        )

        results = index.search('2024', top_k=10)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['url'], 'https://example.com/release-notes')



class TestIndustryIndexPath(unittest.TestCase):
    """Indexer follows extract≠index, O(1) avgdl, optional chunks."""

    def test_chunks_off_by_default(self):
        idx = BM25Index()
        idx.add_document(
            0, 'https://ex.com/py', 'Python Tutorial',
            'Python list comprehension makes code short.',
            headings=[(1, 'List Comprehension')],
        )
        self.assertNotIn('https://ex.com/py#list-comprehension', idx.url_to_id)

    def test_running_avgdl(self):
        idx = BM25Index()
        idx.add_document(0, 'https://a', 'A', 'alpha beta gamma')
        avg1 = idx.avg_doc_length
        idx.add_document(1, 'https://b', 'B', 'alpha')
        # Removing should keep avg consistent with sum/n
        length_sum = sum(idx.doc_lengths.values())
        self.assertAlmostEqual(idx.avg_doc_length, length_sum / len(idx.doc_lengths))
        idx.remove_document(0)
        if idx.doc_lengths:
            self.assertAlmostEqual(
                idx.avg_doc_length,
                sum(idx.doc_lengths.values()) / len(idx.doc_lengths),
            )
        self.assertEqual(idx._total_doc_length, sum(idx.doc_lengths.values()))

    def test_build_trusts_text_without_reparse(self):
        import json
        import tempfile
        from pathlib import Path
        idx = BM25Index()
        with tempfile.TemporaryDirectory() as td:
            pages = Path(td)
            # Misleading raw_html would change title if reparsed; stream/dom
            # would not produce CANONICAL_MARKER from this fake html alone.
            page = {
                'url': 'https://ex.com/doc',
                'title': 'Canonical Title',
                'text': 'canonical body unique_marker_xyz',
                'description': '',
                'headings': [],
                'raw_html': '<html><title>OTHER</title><body>other body</body></html>',
            }
            (pages / 'p.json').write_text(json.dumps(page), encoding='utf-8')
            n = idx.build_from_pages(pages, verbose=False, reparse=False)
            self.assertGreaterEqual(n, 1)
            doc = idx.get_document(idx.get_doc_id('https://ex.com/doc'))
            self.assertEqual(doc['title'], 'Canonical Title')
            # unique token from canonical text should be searchable
            hits = idx.search('unique_marker_xyz', 5)
            self.assertTrue(hits)

    def test_build_reparse_overrides_text(self):
        import json
        import tempfile
        from pathlib import Path
        idx = BM25Index()
        with tempfile.TemporaryDirectory() as td:
            pages = Path(td)
            page = {
                'url': 'https://ex.com/doc',
                'title': 'Old',
                'text': 'old body',
                'description': '',
                'headings': [],
                'raw_html': (
                    '<html><head><title>Fresh Title</title></head>'
                    '<body><main><h1>Fresh Title</h1>'
                    '<p>fresh_reparse_token_zzz content here</p></main></body></html>'
                ),
            }
            (pages / 'p.json').write_text(json.dumps(page), encoding='utf-8')
            idx.build_from_pages(pages, verbose=False, reparse=True, parser='dom')
            doc = idx.get_document(idx.get_doc_id('https://ex.com/doc'))
            self.assertIn('Fresh', doc['title'])
            hits = idx.search('fresh_reparse_token_zzz', 5)
            self.assertTrue(hits)

    def test_skip_genindex_urls(self):
        import json
        import tempfile
        from pathlib import Path
        idx = BM25Index()
        with tempfile.TemporaryDirectory() as td:
            pages = Path(td)
            for name, url in [
                ('a.json', 'https://ex.com/library/os.html'),
                ('b.json', 'https://ex.com/genindex.html'),
            ]:
                (pages / name).write_text(json.dumps({
                    'url': url,
                    'title': 'T',
                    'text': 'hello world content',
                    'headings': [],
                }), encoding='utf-8')
            idx.build_from_pages(pages, verbose=False)
            self.assertTrue(idx.has_url('https://ex.com/library/os.html'))
            self.assertFalse(idx.has_url('https://ex.com/genindex.html'))

    def test_remove_uses_term_list(self):
        idx = BM25Index()
        idx.add_document(0, 'https://a', 'Alpha', 'zebra unique_term_aaa')
        idx.add_document(1, 'https://b', 'Beta', 'zebra unique_term_bbb')
        self.assertIn('unique_term_aaa', idx.index or {})
        # after stemming may differ — check via search
        idx.remove_document(0)
        self.assertFalse(idx.has_url('https://a'))
        self.assertTrue(idx.has_url('https://b'))



if __name__ == '__main__':
    unittest.main()
