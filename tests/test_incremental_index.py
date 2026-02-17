"""Tests for incremental index updates (#141)."""

import json
import tempfile
import unittest
from pathlib import Path

from doc_search.indexer import BM25Index


def _write_page(pages_dir: Path, url: str, title: str, text: str,
                description: str = '', headings: list = None, doc_type: str = 'html'):
    """Write a page JSON file to the pages directory."""
    import hashlib
    page_id = hashlib.sha256(url.encode()).hexdigest()[:16]
    page = {
        'url': url,
        'title': title,
        'text': text,
        'description': description,
        'headings': headings or [],
        'doc_type': doc_type,
    }
    with open(pages_dir / f'{page_id}.json', 'w') as f:
        json.dump(page, f)
    return page_id


def _remove_page(pages_dir: Path, url: str):
    """Remove a page JSON file."""
    import hashlib
    page_id = hashlib.sha256(url.encode()).hexdigest()[:16]
    page_file = pages_dir / f'{page_id}.json'
    if page_file.exists():
        page_file.unlink()


class TestContentHashComputation(unittest.TestCase):
    """Test content hash computation."""

    def test_same_content_same_hash(self):
        page = {'title': 'Hello', 'text': 'World', 'description': '', 'headings': []}
        h1 = BM25Index._compute_content_hash(page)
        h2 = BM25Index._compute_content_hash(page)
        self.assertEqual(h1, h2)

    def test_different_content_different_hash(self):
        p1 = {'title': 'Hello', 'text': 'World', 'description': '', 'headings': []}
        p2 = {'title': 'Hello', 'text': 'Changed', 'description': '', 'headings': []}
        self.assertNotEqual(
            BM25Index._compute_content_hash(p1),
            BM25Index._compute_content_hash(p2)
        )

    def test_hash_is_string(self):
        page = {'title': 'T', 'text': 'X', 'description': '', 'headings': []}
        h = BM25Index._compute_content_hash(page)
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 16)


class TestRemoveDocument(unittest.TestCase):
    """Test the remove_document method."""

    def setUp(self):
        self.index = BM25Index()
        self.index.add_document(0, 'http://a.com/1', 'Alpha', 'alpha beta gamma')
        self.index.add_document(1, 'http://a.com/2', 'Beta', 'beta delta epsilon')

    def test_remove_reduces_count(self):
        self.assertEqual(self.index.total_docs, 2)
        self.index.remove_document(0)
        self.assertEqual(self.index.total_docs, 1)

    def test_remove_clears_url(self):
        self.index.remove_document(0)
        self.assertFalse(self.index.has_url('http://a.com/1'))
        self.assertTrue(self.index.has_url('http://a.com/2'))

    def test_remove_clears_doc_metadata(self):
        self.index.remove_document(0)
        self.assertIsNone(self.index.get_document(0))

    def test_remove_nonexistent_is_noop(self):
        self.index.remove_document(999)
        self.assertEqual(self.index.total_docs, 2)

    def test_search_after_remove(self):
        """Removed doc should not appear in search results."""
        self.index.remove_document(0)
        results = self.index.search('alpha')
        urls = [r['url'] for r in results]
        self.assertNotIn('http://a.com/1', urls)

    def test_remaining_doc_still_searchable(self):
        self.index.remove_document(0)
        results = self.index.search('beta')
        urls = [r['url'] for r in results]
        self.assertIn('http://a.com/2', urls)


class TestBuildFromPagesStoresHashes(unittest.TestCase):
    """Test that build_from_pages populates content_hashes."""

    def test_full_build_stores_hashes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'Page A', 'content of page a')
            _write_page(pages_dir, 'http://x.com/b', 'Page B', 'content of page b')

            index = BM25Index()
            index.build_from_pages(pages_dir, verbose=False)

            self.assertEqual(len(index.content_hashes), 2)
            self.assertIn('http://x.com/a', index.content_hashes)
            self.assertIn('http://x.com/b', index.content_hashes)


class TestIncrementalIndexing(unittest.TestCase):
    """Core incremental indexing tests."""

    def _build_full(self, pages_dir):
        index = BM25Index()
        index.build_from_pages(pages_dir, verbose=False)
        return index

    def test_no_changes(self):
        """When nothing changed, stats should show all unchanged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'alpha content')
            _write_page(pages_dir, 'http://x.com/b', 'B', 'beta content')

            index = self._build_full(pages_dir)
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)

            self.assertEqual(stats['new'], 0)
            self.assertEqual(stats['updated'], 0)
            self.assertEqual(stats['removed'], 0)
            self.assertEqual(stats['unchanged'], 2)
            self.assertEqual(index.total_docs, 2)

    def test_new_page(self):
        """Adding a new page should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'alpha content')

            index = self._build_full(pages_dir)
            self.assertEqual(index.total_docs, 1)

            _write_page(pages_dir, 'http://x.com/b', 'B', 'beta content')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)

            self.assertEqual(stats['new'], 1)
            self.assertEqual(stats['unchanged'], 1)
            self.assertEqual(index.total_docs, 2)

    def test_changed_page(self):
        """Changing page content should be detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'original content')

            index = self._build_full(pages_dir)

            # Overwrite with different content
            _write_page(pages_dir, 'http://x.com/a', 'A Updated', 'modified content completely new')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)

            self.assertEqual(stats['updated'], 1)
            self.assertEqual(stats['new'], 0)
            self.assertEqual(index.total_docs, 1)

    def test_deleted_page(self):
        """Removing a page file should remove it from the index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'alpha content')
            _write_page(pages_dir, 'http://x.com/b', 'B', 'beta content')

            index = self._build_full(pages_dir)
            self.assertEqual(index.total_docs, 2)

            _remove_page(pages_dir, 'http://x.com/b')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)

            self.assertEqual(stats['removed'], 1)
            self.assertEqual(stats['unchanged'], 1)
            self.assertEqual(index.total_docs, 1)
            self.assertFalse(index.has_url('http://x.com/b'))

    def test_mixed_changes(self):
        """Test new + changed + deleted + unchanged simultaneously."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/unchanged', 'U', 'stays the same')
            _write_page(pages_dir, 'http://x.com/to-change', 'C', 'original text')
            _write_page(pages_dir, 'http://x.com/to-delete', 'D', 'will be deleted')

            index = self._build_full(pages_dir)
            self.assertEqual(index.total_docs, 3)

            # Apply changes
            _write_page(pages_dir, 'http://x.com/to-change', 'C2', 'updated text new words')
            _remove_page(pages_dir, 'http://x.com/to-delete')
            _write_page(pages_dir, 'http://x.com/brand-new', 'N', 'brand new page')

            stats = index.build_from_pages_incremental(pages_dir, verbose=False)

            self.assertEqual(stats['new'], 1)
            self.assertEqual(stats['updated'], 1)
            self.assertEqual(stats['removed'], 1)
            self.assertEqual(stats['unchanged'], 1)
            self.assertEqual(index.total_docs, 3)

    def test_search_after_new_page(self):
        """New page content should be searchable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'alpha content')

            index = self._build_full(pages_dir)
            _write_page(pages_dir, 'http://x.com/b', 'B', 'zebra unique term')
            index.build_from_pages_incremental(pages_dir, verbose=False)

            results = index.search('zebra')
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['url'], 'http://x.com/b')

    def test_search_after_update(self):
        """Updated content should be reflected in search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'original oldterm')

            index = self._build_full(pages_dir)
            results = index.search('oldterm')
            self.assertEqual(len(results), 1)

            _write_page(pages_dir, 'http://x.com/a', 'A', 'replacement newterm')
            index.build_from_pages_incremental(pages_dir, verbose=False)

            # Old term should not match
            results = index.search('oldterm')
            self.assertEqual(len(results), 0)

            # New term should match
            results = index.search('newterm')
            self.assertEqual(len(results), 1)

    def test_search_after_delete(self):
        """Deleted page should not appear in search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'unique123 content')
            _write_page(pages_dir, 'http://x.com/b', 'B', 'other stuff')

            index = self._build_full(pages_dir)
            _remove_page(pages_dir, 'http://x.com/a')
            index.build_from_pages_incremental(pages_dir, verbose=False)

            results = index.search('unique123')
            self.assertEqual(len(results), 0)


class TestIncrementalMatchesFullRebuild(unittest.TestCase):
    """Verify incremental produces identical search results to full rebuild."""

    def test_results_match_after_mixed_changes(self):
        """After mixed changes, incremental and full rebuild should give same results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()

            # Initial pages
            _write_page(pages_dir, 'http://x.com/stay', 'Stay', 'python programming language')
            _write_page(pages_dir, 'http://x.com/change', 'Change', 'old content about java')
            _write_page(pages_dir, 'http://x.com/gone', 'Gone', 'will be removed soon')

            # Build initial index
            incr_index = BM25Index()
            incr_index.build_from_pages(pages_dir, verbose=False)

            # Apply changes
            _write_page(pages_dir, 'http://x.com/change', 'Changed', 'new content about rust programming')
            _remove_page(pages_dir, 'http://x.com/gone')
            _write_page(pages_dir, 'http://x.com/added', 'Added', 'fresh javascript tutorial')

            # Incremental update
            incr_index.build_from_pages_incremental(pages_dir, verbose=False)

            # Full rebuild from scratch
            full_index = BM25Index()
            full_index.build_from_pages(pages_dir, verbose=False)

            # Compare search results for various queries
            queries = ['python', 'rust', 'javascript', 'programming', 'java', 'tutorial', 'content']
            for query in queries:
                incr_results = incr_index.search(query, top_k=10)
                full_results = full_index.search(query, top_k=10)

                incr_urls = {r['url'] for r in incr_results}
                full_urls = {r['url'] for r in full_results}
                self.assertEqual(incr_urls, full_urls,
                                 f"URL mismatch for query '{query}': "
                                 f"incremental={incr_urls}, full={full_urls}")

    def test_total_docs_match(self):
        """Total document count should match between incremental and full."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()

            _write_page(pages_dir, 'http://x.com/a', 'A', 'alpha')
            _write_page(pages_dir, 'http://x.com/b', 'B', 'beta')

            incr = BM25Index()
            incr.build_from_pages(pages_dir, verbose=False)

            _write_page(pages_dir, 'http://x.com/c', 'C', 'gamma')
            _remove_page(pages_dir, 'http://x.com/a')
            incr.build_from_pages_incremental(pages_dir, verbose=False)

            full = BM25Index()
            full.build_from_pages(pages_dir, verbose=False)

            self.assertEqual(incr.total_docs, full.total_docs)


class TestSaveLoadPreservesHashes(unittest.TestCase):
    """Test that content_hashes survive save/load cycle."""

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'content here')

            index = BM25Index()
            index.build_from_pages(pages_dir, verbose=False)
            self.assertTrue(len(index.content_hashes) > 0)

            # Save and reload
            save_path = index.save(Path(tmpdir) / 'index')
            loaded = BM25Index.load(save_path)

            self.assertEqual(loaded.content_hashes, index.content_hashes)

    def test_incremental_after_reload(self):
        """Incremental should work after save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'content alpha')

            index = BM25Index()
            index.build_from_pages(pages_dir, verbose=False)
            save_path = index.save(Path(tmpdir) / 'index')

            # Reload and do incremental
            loaded = BM25Index.load(save_path)
            _write_page(pages_dir, 'http://x.com/b', 'B', 'content beta')
            stats = loaded.build_from_pages_incremental(pages_dir, verbose=False)

            self.assertEqual(stats['new'], 1)
            self.assertEqual(stats['unchanged'], 1)
            self.assertEqual(loaded.total_docs, 2)


class TestMultipleIncrementalRounds(unittest.TestCase):
    """Test multiple incremental updates in succession."""

    def test_three_rounds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()

            # Round 1: initial build
            _write_page(pages_dir, 'http://x.com/a', 'A', 'first page')
            index = BM25Index()
            index.build_from_pages(pages_dir, verbose=False)

            # Round 2: add page
            _write_page(pages_dir, 'http://x.com/b', 'B', 'second page')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)
            self.assertEqual(stats['new'], 1)
            self.assertEqual(index.total_docs, 2)

            # Round 3: modify and add
            _write_page(pages_dir, 'http://x.com/a', 'A v2', 'modified first page')
            _write_page(pages_dir, 'http://x.com/c', 'C', 'third page')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)
            self.assertEqual(stats['new'], 1)
            self.assertEqual(stats['updated'], 1)
            self.assertEqual(stats['unchanged'], 1)
            self.assertEqual(index.total_docs, 3)


class TestEdgeCases(unittest.TestCase):
    """Edge case tests for incremental indexing."""

    def test_incremental_on_empty_index(self):
        """Incremental on fresh index with no hashes treats all as new."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'content')

            index = BM25Index()
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)
            self.assertEqual(stats['new'], 1)
            self.assertEqual(index.total_docs, 1)

    def test_incremental_empty_pages_dir(self):
        """Incremental with empty dir should remove all existing docs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'A', 'content')

            index = BM25Index()
            index.build_from_pages(pages_dir, verbose=False)

            # Remove all pages
            _remove_page(pages_dir, 'http://x.com/a')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)
            self.assertEqual(stats['removed'], 1)
            self.assertEqual(index.total_docs, 0)

    def test_title_change_detected(self):
        """Changing only the title should trigger an update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'Original Title', 'same text')

            index = BM25Index()
            index.build_from_pages(pages_dir, verbose=False)

            _write_page(pages_dir, 'http://x.com/a', 'New Title', 'same text')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)
            self.assertEqual(stats['updated'], 1)

    def test_description_change_detected(self):
        """Changing only description should trigger an update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pages_dir = Path(tmpdir) / 'pages'
            pages_dir.mkdir()
            _write_page(pages_dir, 'http://x.com/a', 'T', 'text', description='old desc')

            index = BM25Index()
            index.build_from_pages(pages_dir, verbose=False)

            _write_page(pages_dir, 'http://x.com/a', 'T', 'text', description='new desc')
            stats = index.build_from_pages_incremental(pages_dir, verbose=False)
            self.assertEqual(stats['updated'], 1)


if __name__ == '__main__':
    unittest.main()
