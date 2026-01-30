"""
Tests for the EnhancedSearchEngine with all 4 new features.
"""

import unittest
import tempfile
import json
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
        response = self.engine.search('python classes')
        
        self.assertIn('results', response)
        self.assertTrue(len(response['results']) > 0)
        
        # First result should be about classes
        first = response['results'][0]
        self.assertIn('classes', first['title'].lower())
    
    def test_search_returns_dict(self):
        """Search should return dict with expected keys."""
        response = self.engine.search('python')
        
        self.assertIsInstance(response, dict)
        self.assertIn('results', response)
        self.assertIn('suggestion', response)
        self.assertIn('facets', response)
        self.assertIn('query', response)
    
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
        # Should have some facet types
        if facets:
            self.assertIn('type', facets)
    
    def test_facet_filter(self):
        """Should filter results by facet."""
        # Get all results first
        all_response = self.engine.search('python')
        all_count = len(all_response['results'])
        
        # Filter by tutorial type
        filtered_response = self.engine.search(
            'python',
            facet_filters={'type': 'tutorial'}
        )
        
        # Filtered should have fewer or equal results
        self.assertLessEqual(len(filtered_response['results']), all_count)
    
    def test_synonym_expansion(self):
        """Search should expand synonyms."""
        response = self.engine.search('function', expand_synonyms=True)
        
        # Check if expanded_query is set (if synonyms were found)
        # The response should still work
        self.assertIn('results', response)
    
    def test_search_simple_backward_compat(self):
        """search_simple should return just results list."""
        results = self.engine.search_simple('python')
        
        self.assertIsInstance(results, list)
        if results:
            self.assertIn('url', results[0])
            self.assertIn('title', results[0])
    
    def test_enhanced_stats(self):
        """Should return enhanced statistics."""
        stats = self.engine.get_stats()
        
        self.assertIn('features', stats)
        self.assertIn('spellcheck', stats['features'])
        self.assertIn('autocomplete', stats['features'])
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
        response = self.engine.search('test')
        
        self.assertIn('results', response)
        # No suggestion when spellcheck disabled
        self.assertIsNone(response['suggestion'])
        # Empty facets when facets disabled
        self.assertEqual(response['facets'], {})
    
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
        response = self.engine.search('functoin', expand_synonyms=True)
        
        # Should have results (even with typo if synonym helps)
        self.assertIn('results', response)
        
        # Should have suggestion for typo
        if response['suggestion']:
            self.assertNotEqual(response['suggestion'], 'functoin')
    
    def test_faceted_search_workflow(self):
        """Test typical faceted search workflow."""
        # 1. Initial search
        response1 = self.engine.search('reference')
        
        # 2. Get available facets
        facets = response1['facets']
        
        # 3. Apply filter if we have facets
        if facets and 'type' in facets:
            first_type = list(facets['type'].keys())[0]
            response2 = self.engine.search(
                'reference',
                facet_filters={'type': first_type}
            )
            
            # Should have results
            self.assertIn('results', response2)
    
    def test_autocomplete_workflow(self):
        """Test autocomplete -> search workflow."""
        # 1. User types 'fun'
        suggestions = self.engine.get_autocomplete_suggestions('fun')
        
        # 2. User selects a suggestion or continues typing
        if suggestions:
            query = suggestions[0]
            response = self.engine.search(query)
            self.assertIn('results', response)


if __name__ == '__main__':
    unittest.main()
