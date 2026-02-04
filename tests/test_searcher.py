
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
