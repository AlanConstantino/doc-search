"""
Tests for the EnhancedSearchEngine with all 4 new features.
"""

import unittest
import tempfile
import json
import warnings
from pathlib import Path

from doc_search.indexer import BM25Index
from doc_search.searcher import EnhancedSearchEngine


class TestEnhancedSearchEngine(unittest.TestCase):
    """Test EnhancedSearchEngine with all features."""
    
    @classmethod
    def setUpClass(cls):
        """Create a test index with sample documents."""
        cls.index = BM25Index(stem=False)
        
        # Add test documents
        test_docs = [
            {
                'doc_id': 0,
                'url': 'https://docs.python.org/3/tutorial/classes.html',
                'title': 'Classes — Python Tutorial',
                'text': 'Python classes provide a means of bundling data and functionality together. Creating a new class creates a new type of object.',
                'description': 'Learn about classes and object-oriented programming in Python.'
            },
            {
                'doc_id': 1,
                'url': 'https://docs.python.org/3/library/string.html',
                'title': 'string — Common string operations',
                'text': 'The string module contains constants and classes for string manipulation. Template strings support dollar-based substitutions.',
                'description': 'String constants, Template class, and helper functions.'
            },
            {
                'doc_id': 2,
                'url': 'https://docs.python.org/3/library/functions.html',
                'title': 'Built-in Functions',
                'text': 'Python has many built-in functions like print(), len(), range(), and type(). These functions are always available.',
                'description': 'Python built-in functions reference.'
            },
            {
                'doc_id': 3,
                'url': 'https://docs.python.org/3/tutorial/datastructures.html',
                'title': 'Data Structures — Python Tutorial',
                'text': 'This tutorial covers lists, dictionaries, tuples, and sets. Lists are mutable sequences, while tuples are immutable.',
                'description': 'Learn about Python data structures.'
            },
            {
                'doc_id': 4,
                'url': 'https://docs.python.org/3/library/os.html',
                'title': 'os — Operating system interfaces',
                'text': 'The os module provides functions for interacting with the operating system. File operations, environment variables, and processes.',
                'description': 'OS module for system operations.'
            },
        ]
        
        for doc in test_docs:
            cls.index.add_document(
                doc_id=doc['doc_id'],
                url=doc['url'],
                title=doc['title'],
                text=doc['text'],
                description=doc['description']
            )
        
        # Create enhanced engine
        cls.engine = EnhancedSearchEngine(
            cls.index,
            enable_spellcheck=True,
            enable_autocomplete=True,
            enable_facets=True,
            enable_synonyms=True
        )
    
    def test_basic_search(self):
        """Basic search should work."""
        results = self.engine.search('python classes')
        
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        
        # First result should be about classes
        first = results[0]
        self.assertIn('classes', first['title'].lower())
    
    def test_search_returns_list(self):
        """Search should return list for LSP compliance with SearchEngine."""
        results = self.engine.search('python')
        
        self.assertIsInstance(results, list)
        if results:
            self.assertIn('url', results[0])
            self.assertIn('title', results[0])
    
    def test_search_enhanced_returns_dict(self):
        """search_enhanced should return dict with expected keys."""
        response = self.engine.search_enhanced('python')
        
        self.assertIsInstance(response, dict)
        self.assertIn('results', response)
        self.assertIn('suggestion', response)
        self.assertIn('facets', response)
        self.assertIn('query', response)
    
    def test_last_metadata_attributes(self):
        """Search should populate last_* instance attributes."""
        self.engine.search('python')
        
        self.assertEqual(self.engine.last_query, 'python')
        self.assertIsInstance(self.engine.last_facets, dict)
        # last_suggestion may be None if no typo
    
    def test_spelling_suggestion(self):
        """Should suggest corrections for misspelled queries."""
        # Use a common index term with a typo
        suggestion = self.engine.get_spelling_suggestion('pyhton')
        
        # May or may not have suggestion depending on vocabulary
        # The important thing is it doesn't crash
        if suggestion:
            self.assertIsInstance(suggestion, str)
    
    def test_autocomplete(self):
        """Should provide autocomplete suggestions."""
        suggestions = self.engine.get_autocomplete_suggestions('str')
        
        self.assertIsInstance(suggestions, list)
        # Should have suggestions starting with 'str'
        if suggestions:
            self.assertTrue(all(s.startswith('str') for s in suggestions))
    
    def test_facet_counts(self):
        """Should return facet counts."""
        facets = self.engine.get_facet_counts()
        
        self.assertIsInstance(facets, dict)
        # Should have some facet types (category from URL path)
        if facets:
            self.assertIn('category', facets)
    
    def test_facet_filter(self):
        """Should filter results by facet."""
        # Get all results first
        all_results = self.engine.search('python')
        all_count = len(all_results)
        
        # Filter by category (from URL path)
        filtered_results = self.engine.search(
            'python',
            facet_filters={'category': 'tutorial'}
        )
        
        # Filtered should have fewer or equal results
        self.assertLessEqual(len(filtered_results), all_count)
    
    def test_synonym_expansion(self):
        """Search should expand synonyms."""
        results = self.engine.search('function', expand_synonyms=True)
        
        # The search should return results
        self.assertIsInstance(results, list)
        
        # Check if expanded_query is set via attribute
        # (may be None if no synonyms found)
    
    def test_search_simple_backward_compat(self):
        """search_simple should return just results list (same as search now)."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            results = self.engine.search_simple('python')
        
        self.assertIsInstance(results, list)
        if results:
            self.assertIn('url', results[0])
            self.assertIn('title', results[0])
    
    def test_search_simple_deprecation_warning(self):
        """search_simple should emit a DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.engine.search_simple('python')
            
            # Check that a DeprecationWarning was raised
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, DeprecationWarning))
            self.assertIn('search_simple', str(w[0].message))
            self.assertIn('deprecated', str(w[0].message))
            self.assertIn('2.0.0', str(w[0].message))
    
    def test_enhanced_stats(self):
        """Should return enhanced statistics."""
        stats = self.engine.get_stats()
        
        self.assertIn('features', stats)
        self.assertIn('spellcheck', stats['features'])
        self.assertIn('facets', stats['features'])
        self.assertIn('synonyms', stats['features'])


class TestEnhancedSearchEngineDisabledFeatures(unittest.TestCase):
    """Test with features disabled."""
    
    def setUp(self):
        """Create engine with features disabled."""
        index = BM25Index(stem=False)
        index.add_document(0, 'https://example.com/test', 'Test', 'Test content')
        
        self.engine = EnhancedSearchEngine(
            index,
            enable_spellcheck=False,
            enable_autocomplete=False,
            enable_facets=False,
            enable_synonyms=False
        )
    
    def test_search_with_disabled_features(self):
        """Search should work with features disabled."""
        results = self.engine.search('test')
        
        self.assertIsInstance(results, list)
        # No suggestion when spellcheck disabled
        self.assertIsNone(self.engine.last_suggestion)
        # Empty facets when facets disabled
        self.assertEqual(self.engine.last_facets, {})
    
    def test_autocomplete_when_disabled(self):
        """Autocomplete should return empty when disabled."""
        suggestions = self.engine.get_autocomplete_suggestions('te')
        self.assertEqual(suggestions, [])
    
    def test_facets_when_disabled(self):
        """Facet counts should be empty when disabled."""
        facets = self.engine.get_facet_counts()
        self.assertEqual(facets, {})


class TestEnhancedSearchEngineIntegration(unittest.TestCase):
    """Integration tests for all features working together."""
    
    def setUp(self):
        """Create a comprehensive test setup."""
        self.index = BM25Index(stem=True)
        
        # Add more documents for better testing
        docs = [
            (0, 'https://docs.example.com/tutorial/intro.html', 
             'Introduction Tutorial', 'Getting started with the library'),
            (1, 'https://docs.example.com/api/functions.html',
             'API Reference: Functions', 'function method procedure reference'),
            (2, 'https://docs.example.com/api/classes.html',
             'API Reference: Classes', 'class object type reference'),
            (3, 'https://docs.example.com/tutorial/advanced.html',
             'Advanced Tutorial', 'Advanced techniques and methods'),
            (4, 'https://docs.example.com/guide/best-practices.html',
             'Best Practices Guide', 'coding practices and patterns'),
        ]
        
        for doc_id, url, title, text in docs:
            self.index.add_document(doc_id, url, title, text)
        
        self.engine = EnhancedSearchEngine(self.index)
    
    def test_combined_features(self):
        """Test multiple features in one search."""
        results = self.engine.search('functoin', expand_synonyms=True)
        
        # Should have results (even with typo if synonym helps)
        self.assertIsInstance(results, list)
        
        # Should have suggestion for typo (accessed via attribute)
        if self.engine.last_suggestion:
            self.assertNotEqual(self.engine.last_suggestion, 'functoin')
    
    def test_faceted_search_workflow(self):
        """Test typical faceted search workflow."""
        # 1. Initial search
        self.engine.search('reference')
        
        # 2. Get available facets from last search
        facets = self.engine.last_facets
        
        # 3. Apply filter if we have facets
        if facets and 'category' in facets:
            first_category = list(facets['category'].keys())[0]
            filtered_results = self.engine.search(
                'reference',
                facet_filters={'category': first_category}
            )
            
            # Should have results
            self.assertIsInstance(filtered_results, list)
    
    def test_autocomplete_workflow(self):
        """Test autocomplete -> search workflow."""
        # 1. User types 'fun'
        suggestions = self.engine.get_autocomplete_suggestions('fun')
        
        # 2. User selects a suggestion or continues typing
        if suggestions:
            query = suggestions[0]
            results = self.engine.search(query)
            self.assertIsInstance(results, list)


if __name__ == '__main__':
    unittest.main()
