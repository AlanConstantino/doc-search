
"""
Tests for the SearchCache and SearchEngine caching functionality.
"""

import unittest
import time

from doc_search.searcher import SearchCache, SearchEngine
from doc_search.indexer import BM25Index


# ============================================================================
# SearchCache Tests
# ============================================================================

class TestSearchCache(unittest.TestCase):
    """Tests for SearchCache class."""
    
    def test_basic_get_set(self):
        """Should store and retrieve cached results."""
        cache = SearchCache(maxsize=10, ttl=300)
        
        results = [{'url': 'https://example.com', 'title': 'Test'}]
        cache.set('test query', results, top_k=10)
        
        cached = cache.get('test query', top_k=10)
        self.assertEqual(cached, results)
    
    def test_cache_miss(self):
        """Should return None for cache miss."""
        cache = SearchCache(maxsize=10, ttl=300)
        
        cached = cache.get('nonexistent', top_k=10)
        self.assertIsNone(cached)
    
    def test_different_params_different_keys(self):
        """Should cache separately for different parameters."""
        cache = SearchCache(maxsize=10, ttl=300)
        
        results1 = [{'url': 'https://example.com/1'}]
        results2 = [{'url': 'https://example.com/2'}]
        
        cache.set('query', results1, top_k=10)
        cache.set('query', results2, top_k=20)
        
        self.assertEqual(cache.get('query', top_k=10), results1)
        self.assertEqual(cache.get('query', top_k=20), results2)
    
    def test_lru_eviction(self):
        """Should evict least recently used when at capacity."""
        cache = SearchCache(maxsize=2, ttl=300)
        
        cache.set('query1', ['r1'], top_k=10)
        cache.set('query2', ['r2'], top_k=10)
        cache.set('query3', ['r3'], top_k=10)  # Should evict query1
        
        self.assertIsNone(cache.get('query1', top_k=10))
        self.assertEqual(cache.get('query2', top_k=10), ['r2'])
        self.assertEqual(cache.get('query3', top_k=10), ['r3'])
    
    def test_ttl_expiration(self):
        """Should expire entries after TTL."""
        cache = SearchCache(maxsize=10, ttl=0.1)  # 100ms TTL
        
        cache.set('query', ['result'], top_k=10)
        
        # Should be present immediately
        self.assertIsNotNone(cache.get('query', top_k=10))
        
        # Wait for TTL to expire
        import time
        time.sleep(0.15)
        
        # Should be expired
        self.assertIsNone(cache.get('query', top_k=10))
    
    def test_no_ttl(self):
        """Should not expire when TTL is None."""
        cache = SearchCache(maxsize=10, ttl=None)
        
        cache.set('query', ['result'], top_k=10)
        
        # Should persist
        self.assertIsNotNone(cache.get('query', top_k=10))
    
    def test_stats(self):
        """Should track cache statistics."""
        cache = SearchCache(maxsize=10, ttl=300)
        
        cache.set('query', ['result'], top_k=10)
        cache.get('query', top_k=10)  # Hit
        cache.get('query', top_k=10)  # Hit
        cache.get('missing', top_k=10)  # Miss
        
        stats = cache.stats()
        self.assertEqual(stats['hits'], 2)
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['size'], 1)
        self.assertEqual(stats['hit_rate'], '66.7%')
    
    def test_clear(self):
        """Should clear all cached entries."""
        cache = SearchCache(maxsize=10, ttl=300)
        
        cache.set('query1', ['r1'], top_k=10)
        cache.set('query2', ['r2'], top_k=10)
        
        cache.clear()
        
        self.assertIsNone(cache.get('query1', top_k=10))
        self.assertIsNone(cache.get('query2', top_k=10))
        self.assertEqual(cache.stats()['size'], 0)


class TestSearchEngineCaching(unittest.TestCase):
    """Tests for SearchEngine caching integration."""
    
    def setUp(self):
        """Create test index."""
        self.index = BM25Index()
        docs = [
            {'url': 'https://example.com/1', 'title': 'Python Tutorial', 
             'text': 'Learn Python programming language basics'},
            {'url': 'https://example.com/2', 'title': 'Python Functions',
             'text': 'Functions in Python are defined with def keyword'},
        ]
        for i, doc in enumerate(docs):
            self.index.add_document(i, doc['url'], doc['title'], doc['text'])
    
    def test_caching_disabled_by_default(self):
        """Caching should be disabled when cache_size=0."""
        engine = SearchEngine(self.index, cache_size=0)
        self.assertFalse(engine.cache_enabled)
        self.assertIsNone(engine.get_cache_stats())
    
    def test_caching_enabled(self):
        """Caching should be enabled when cache_size > 0."""
        engine = SearchEngine(self.index, cache_size=10)
        self.assertTrue(engine.cache_enabled)
        self.assertIsNotNone(engine.get_cache_stats())
    
    def test_search_uses_cache(self):
        """Search should use cache for repeated queries."""
        engine = SearchEngine(self.index, cache_size=10)
        
        # First search - cache miss
        results1 = engine.search('python', top_k=10)
        stats1 = engine.get_cache_stats()
        self.assertEqual(stats1['misses'], 1)
        self.assertEqual(stats1['hits'], 0)
        
        # Second search - cache hit
        results2 = engine.search('python', top_k=10)
        stats2 = engine.get_cache_stats()
        self.assertEqual(stats2['misses'], 1)
        self.assertEqual(stats2['hits'], 1)
        
        # Results should be the same
        self.assertEqual(results1, results2)
    
    def test_clear_cache(self):
        """clear_cache should clear all cached results."""
        engine = SearchEngine(self.index, cache_size=10)
        
        engine.search('python', top_k=10)
        self.assertEqual(engine.get_cache_stats()['size'], 1)
        
        engine.clear_cache()
        self.assertEqual(engine.get_cache_stats()['size'], 0)


# ============================================================================
# Persistent Cache Tests
# ============================================================================

class TestPersistentCache(unittest.TestCase):
    """Tests for persistent (SQLite-backed) cache functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        import tempfile
        import os
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = os.path.join(self.temp_dir, 'test_cache.db')
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_persistent_cache_creates_db(self):
        """Should create SQLite database file when cache_path is provided."""
        import os
        from pathlib import Path
        
        cache = SearchCache(maxsize=10, ttl=300, cache_path=Path(self.cache_path))
        
        self.assertTrue(os.path.exists(self.cache_path))
        cache.close()
    
    def test_persistent_cache_survives_restart(self):
        """Cache entries should survive cache recreation (simulated restart)."""
        from pathlib import Path
        
        # Create cache and add entries
        cache1 = SearchCache(maxsize=10, ttl=300, cache_path=Path(self.cache_path))
        cache1.set('query1', ['result1'], top_k=10)
        cache1.set('query2', ['result2'], top_k=5)
        cache1.close()
        
        # Create new cache instance (simulates restart)
        cache2 = SearchCache(maxsize=10, ttl=300, cache_path=Path(self.cache_path))
        
        # Entries should be restored
        self.assertEqual(cache2.get('query1', top_k=10), ['result1'])
        self.assertEqual(cache2.get('query2', top_k=5), ['result2'])
        cache2.close()
    
    def test_persistent_cache_respects_ttl_on_load(self):
        """Expired entries should be pruned when loading from disk."""
        from pathlib import Path
        
        # Create cache with short TTL
        cache1 = SearchCache(maxsize=10, ttl=0.1, cache_path=Path(self.cache_path))
        cache1.set('query', ['result'], top_k=10)
        cache1.close()
        
        # Wait for TTL to expire
        time.sleep(0.15)
        
        # Create new cache - expired entries should be pruned
        cache2 = SearchCache(maxsize=10, ttl=0.1, cache_path=Path(self.cache_path))
        self.assertIsNone(cache2.get('query', top_k=10))
        cache2.close()
    
    def test_persistent_cache_clear(self):
        """Clear should remove entries from both memory and disk."""
        from pathlib import Path
        
        # Create and populate cache
        cache1 = SearchCache(maxsize=10, ttl=300, cache_path=Path(self.cache_path))
        cache1.set('query', ['result'], top_k=10)
        cache1.clear()
        cache1.close()
        
        # New instance should not have the entry
        cache2 = SearchCache(maxsize=10, ttl=300, cache_path=Path(self.cache_path))
        self.assertIsNone(cache2.get('query', top_k=10))
        cache2.close()
    
    def test_persistent_cache_lru_eviction(self):
        """LRU eviction should also remove from disk."""
        from pathlib import Path
        
        cache = SearchCache(maxsize=2, ttl=300, cache_path=Path(self.cache_path))
        cache.set('query1', ['r1'], top_k=10)
        cache.set('query2', ['r2'], top_k=10)
        cache.set('query3', ['r3'], top_k=10)  # Should evict query1
        cache.close()
        
        # Reload and verify query1 was evicted from disk too
        cache2 = SearchCache(maxsize=2, ttl=300, cache_path=Path(self.cache_path))
        self.assertIsNone(cache2.get('query1', top_k=10))
        self.assertEqual(cache2.get('query2', top_k=10), ['r2'])
        self.assertEqual(cache2.get('query3', top_k=10), ['r3'])
        cache2.close()
    
    def test_persistent_cache_stats(self):
        """Stats should indicate persistent mode."""
        from pathlib import Path
        
        cache = SearchCache(maxsize=10, ttl=300, cache_path=Path(self.cache_path))
        stats = cache.stats()
        
        self.assertTrue(stats['persistent'])
        self.assertEqual(stats['cache_path'], self.cache_path)
        cache.close()
    
    def test_in_memory_cache_stats(self):
        """In-memory cache stats should indicate non-persistent mode."""
        cache = SearchCache(maxsize=10, ttl=300)
        stats = cache.stats()
        
        self.assertFalse(stats['persistent'])
        self.assertIsNone(stats['cache_path'])


class TestSearchEnginePersistentCache(unittest.TestCase):
    """Tests for SearchEngine with persistent cache."""
    
    def setUp(self):
        """Create test index and temp directory."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = f"{self.temp_dir}/engine_cache.db"
        
        self.index = BM25Index()
        docs = [
            {'url': 'https://example.com/1', 'title': 'Python Tutorial', 
             'text': 'Learn Python programming language basics'},
            {'url': 'https://example.com/2', 'title': 'Python Functions',
             'text': 'Functions in Python are defined with def keyword'},
        ]
        for i, doc in enumerate(docs):
            self.index.add_document(i, doc['url'], doc['title'], doc['text'])
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_engine_persistent_cache(self):
        """SearchEngine should use persistent cache when cache_path is provided."""
        from pathlib import Path
        import os
        
        engine = SearchEngine(
            self.index, 
            cache_size=10, 
            cache_path=Path(self.cache_path)
        )
        
        # Perform search
        results1 = engine.search('python', top_k=10)
        
        # Check DB file exists
        self.assertTrue(os.path.exists(self.cache_path))
        
        stats = engine.get_cache_stats()
        self.assertTrue(stats['persistent'])


# ============================================================================
# Index Fingerprint / Cache Invalidation Tests
# ============================================================================

class TestIndexFingerprint(unittest.TestCase):
    """Tests for automatic cache invalidation when index changes."""
    
    def setUp(self):
        """Set up test fixtures."""
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.cache_path = f"{self.temp_dir}/fingerprint_cache.db"
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_fingerprint_computed(self):
        """compute_index_fingerprint should return consistent fingerprint."""
        from doc_search.searcher import compute_index_fingerprint
        
        index = BM25Index()
        index.add_document(0, 'https://example.com/1', 'Title 1', 'Content 1')
        index.add_document(1, 'https://example.com/2', 'Title 2', 'Content 2')
        
        fp1 = compute_index_fingerprint(index)
        fp2 = compute_index_fingerprint(index)
        
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 16)  # 16 hex chars
    
    def test_fingerprint_changes_on_add(self):
        """Fingerprint should change when document is added."""
        from doc_search.searcher import compute_index_fingerprint
        
        index = BM25Index()
        index.add_document(0, 'https://example.com/1', 'Title 1', 'Content 1')
        
        fp1 = compute_index_fingerprint(index)
        
        index.add_document(1, 'https://example.com/2', 'Title 2', 'Content 2')
        
        fp2 = compute_index_fingerprint(index)
        
        self.assertNotEqual(fp1, fp2)
    
    def test_fingerprint_changes_on_url_change(self):
        """Fingerprint should change when URLs change."""
        from doc_search.searcher import compute_index_fingerprint
        
        index1 = BM25Index()
        index1.add_document(0, 'https://example.com/old', 'Title', 'Content')
        
        index2 = BM25Index()
        index2.add_document(0, 'https://example.com/new', 'Title', 'Content')
        
        self.assertNotEqual(
            compute_index_fingerprint(index1),
            compute_index_fingerprint(index2)
        )
    
    def test_cache_invalidated_on_reindex(self):
        """Cache should be cleared when index fingerprint changes."""
        from pathlib import Path
        
        # Create index and cache with some data
        index1 = BM25Index()
        index1.add_document(0, 'https://example.com/1', 'Python', 'Python content')
        
        engine1 = SearchEngine(
            index1,
            cache_size=10,
            cache_path=Path(self.cache_path)
        )
        engine1.search('python', top_k=10)
        
        # Verify cache has entry
        self.assertEqual(engine1.get_cache_stats()['size'], 1)
        
        # Create NEW index with different content (simulates re-index)
        index2 = BM25Index()
        index2.add_document(0, 'https://example.com/1', 'Python', 'Python content')
        index2.add_document(1, 'https://example.com/2', 'Java', 'Java content')
        
        # Create new engine with same cache path but different index
        engine2 = SearchEngine(
            index2,
            cache_size=10,
            cache_path=Path(self.cache_path)
        )
        
        # Cache should have been invalidated (size = 0)
        self.assertEqual(engine2.get_cache_stats()['size'], 0)
    
    def test_cache_preserved_when_index_unchanged(self):
        """Cache should be preserved when index fingerprint matches."""
        from pathlib import Path
        
        # Create index and cache with some data
        index1 = BM25Index()
        index1.add_document(0, 'https://example.com/1', 'Python', 'Python content')
        
        engine1 = SearchEngine(
            index1,
            cache_size=10,
            cache_path=Path(self.cache_path)
        )
        engine1.search('python', top_k=10)
        self.assertEqual(engine1.get_cache_stats()['size'], 1)
        
        # Create identical index (simulates restart without re-index)
        index2 = BM25Index()
        index2.add_document(0, 'https://example.com/1', 'Python', 'Python content')
        
        # Create new engine - cache should be preserved
        engine2 = SearchEngine(
            index2,
            cache_size=10,
            cache_path=Path(self.cache_path)
        )
        
        # Cache should still have the entry
        self.assertEqual(engine2.get_cache_stats()['size'], 1)
        
        # And we should get a cache hit
        engine2.search('python', top_k=10)
        self.assertEqual(engine2.get_cache_stats()['hits'], 1)
