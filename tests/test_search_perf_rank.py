"""Tests for faster search + better ranking features (stdlib-only)."""

import os
import tempfile
import unittest
from pathlib import Path

from doc_search.indexer import BM25Index, find_index_path
from doc_search.utils import tokenize, tokenize_with_exact
from doc_search.click_log import ClickLog
from doc_search.searcher import SearchCache, SearchEngine


class TestCodeAwareTokenize(unittest.TestCase):
    def test_camel_snake_dotted(self):
        toks = tokenize('getUserName snake_case os.path.join')
        self.assertIn('user', toks)
        self.assertIn('name', toks)
        self.assertIn('snake', toks)
        self.assertIn('path', toks)
        self.assertIn('join', toks)

    def test_exact_and_stem(self):
        stemmed, exact = tokenize_with_exact('running files', True)
        self.assertEqual(exact, ['running', 'files'])
        self.assertEqual(stemmed, ['run', 'file'])


class TestFieldedBM25AndBigrams(unittest.TestCase):
    def setUp(self):
        self.idx = BM25Index()
        self.idx.add_document(
            0, 'https://ex.com/py', 'Python Tutorial',
            'Python list comprehension makes code short.',
            headings=[(1, 'List Comprehension')],
            index_chunks=True,
        )
        self.idx.add_document(
            1, 'https://ex.com/java', 'Java Guide',
            'Java streams and collections tutorial.',
        )
        self.idx.rebuild_idf_cache()

    def test_title_query_ranks_title_match(self):
        top = self.idx.search('python tutorial', 3)
        self.assertTrue(top)
        self.assertIn('py', top[0]['url'])

    def test_phrase_bigrams(self):
        self.assertTrue(
            self.idx.has_phrase_bigrams(['list', 'comprehension'], 'https://ex.com/py')
        )
        self.assertFalse(
            self.idx.has_phrase_bigrams(['list', 'comprehension'], 'https://ex.com/java')
        )

    def test_section_chunks(self):
        self.assertIn('https://ex.com/py#list-comprehension', self.idx.url_to_id)

    def test_preview_in_doc(self):
        doc = self.idx.get_document(0)
        self.assertTrue(doc.get('preview'))
        self.assertIn('Python', doc['preview'])

    def test_prior_present(self):
        self.assertIn('prior', self.idx.get_document(0))


class TestBinaryIndexAndHeap(unittest.TestCase):
    def test_roundtrip_pkl(self):
        idx = BM25Index()
        idx.add_document(0, 'https://a', 'Alpha', 'alpha beta gamma content here')
        idx.add_document(1, 'https://b', 'Beta', 'beta delta content here')
        idx.rebuild_idf_cache()
        with tempfile.TemporaryDirectory() as td:
            path = idx.save(Path(td) / 'index')
            self.assertTrue(str(path).endswith('.pkl.gz'))
            loaded = BM25Index.load(path)
            self.assertEqual(loaded.total_docs, idx.total_docs)
            self.assertTrue(loaded._idf_cache)
            r = loaded.search('alpha', 5)
            self.assertTrue(r)
            self.assertEqual(r[0]['url'], 'https://a')
            # find_index_path
            found = find_index_path(Path(td))
            self.assertIsNotNone(found)


class TestClickLogCTR(unittest.TestCase):
    def test_clicks_boost_url(self):
        idx = BM25Index()
        idx.add_document(0, 'https://a', 'Shared Topic', 'shared topic document one')
        idx.add_document(1, 'https://b', 'Shared Topic', 'shared topic document two')
        idx.rebuild_idf_cache()
        before = [r['url'] for r in idx.search('shared topic', 2)]
        idx.set_click_counts({'https://b': 50})
        after = [r['url'] for r in idx.search('shared topic', 2)]
        self.assertEqual(after[0], 'https://b')

    def test_click_log_persist(self):
        with tempfile.TemporaryDirectory() as td:
            cl = ClickLog(str(Path(td) / 'clicks.db'))
            cl.log('q', 'https://x', 1)
            cl.log('q', 'https://x', 2)
            cl.log('q', 'https://y', 1)
            counts = cl.counts()
            self.assertEqual(counts['https://x'], 2)
            self.assertEqual(counts['https://y'], 1)


class TestCacheNormalize(unittest.TestCase):
    def test_normalize_query(self):
        self.assertEqual(SearchCache.normalize_query('  Foo   BAR '), 'foo bar')

    def test_cache_key_collapses_ws(self):
        c = SearchCache(maxsize=8)
        c.set('Hello   World', ['r1'], top_k=5)
        hit = c.get('hello world', top_k=5)
        self.assertEqual(hit, ['r1'])


class TestPreviewAvoidsDisk(unittest.TestCase):
    def test_engine_uses_preview(self):
        idx = BM25Index()
        idx.add_document(0, 'https://a', 'Hello World', 'Hello world body text for snippets and ranking.')
        idx.rebuild_idf_cache()
        eng = SearchEngine(idx, pages_dir=None)
        results = eng.search('hello', top_k=5)
        self.assertTrue(results)
        self.assertTrue(results[0].get('snippet') or results[0].get('description'))


if __name__ == '__main__':
    unittest.main()


class TestIndustryRanking(unittest.TestCase):
    """First-stage BM25: coordination, title preference, weighted expansions."""

    def test_multi_term_beats_single_term_cousin(self):
        idx = BM25Index()
        idx.add_document(0, 'https://a', 'List Comprehension',
                         'List comprehension is a python feature for lists.')
        idx.add_document(1, 'https://b', 'Comprehension Only',
                         'Comprehension appears many times. comprehension comprehension.')
        idx.rebuild_idf_cache()
        top = idx.search('list comprehension', 5)
        self.assertEqual(top[0]['url'], 'https://a')
        self.assertGreaterEqual(top[0].get('_term_coverage', 0), 0.99)

    def test_title_match_ranks_above_body_only(self):
        idx = BM25Index()
        idx.add_document(0, 'https://title', 'Asyncio Gather Guide',
                         'This page is about concurrent programming helpers.')
        idx.add_document(1, 'https://body', 'Misc Notes',
                         'You can use asyncio gather for concurrent tasks. ' * 5)
        idx.rebuild_idf_cache()
        top = idx.search('asyncio gather', 5)
        self.assertEqual(top[0]['url'], 'https://title')


    def test_async_with_is_multi_term(self):
        """async with must rank the page that has both terms / bigram."""
        idx = BM25Index()
        idx.add_document(
            0, 'https://async-with', 'Async With Statement',
            'Use async with lock to acquire asynchronously. async with is special.',
        )
        idx.add_document(
            1, 'https://async-only', 'Asyncio Primer',
            'async async async functions and coroutines everywhere async.',
        )
        idx.rebuild_idf_cache()
        top = idx.search('async with', 5)
        self.assertTrue(top)
        self.assertEqual(top[0]['url'], 'https://async-with')
        self.assertGreaterEqual(top[0].get('_term_coverage', 0), 0.99)

    def test_quoted_multi_word_phrase(self):
        from doc_search.searcher import SearchEngine
        idx = BM25Index()
        idx.add_document(0, 'https://a', 'A', 'foo bar appears together as foo bar here')
        idx.add_document(1, 'https://b', 'B', 'foo something bar far apart')
        idx.rebuild_idf_cache()
        eng = SearchEngine(idx)
        # phrase filter path
        hits = eng.search('"foo bar"', top_k=5)
        urls = [h['url'] for h in hits]
        self.assertIn('https://a', urls)

    def test_expansion_weights_prefer_original_terms(self):
        idx = BM25Index()
        idx.add_document(0, 'https://orig', 'Error Handling',
                         'How to handle error conditions in code.')
        idx.add_document(1, 'https://syn', 'Exception Handling',
                         'How to handle exception conditions in code.')
        idx.rebuild_idf_cache()
        # Without weights, both may compete; with error=1.0 exception=0.5, orig wins
        top = idx.search(
            'error exception',
            5,
            term_weights={'error': 1.0, 'exception': 0.5},
        )
        self.assertEqual(top[0]['url'], 'https://orig')

