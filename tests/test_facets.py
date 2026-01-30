"""
Tests for faceted search functionality.
"""

import unittest
from doc_search.facets import FacetExtractor, FacetIndex


class TestFacetExtractor(unittest.TestCase):
    """Test facet extraction logic."""
    
    def test_extract_section_from_h1(self):
        """Should extract section from h1 heading."""
        headings = [(1, 'Built-in Functions'), (2, 'Overview')]
        section = FacetExtractor.extract_section('', headings)
        self.assertEqual(section, 'built in functions')
    
    def test_extract_section_from_title(self):
        """Should extract section from title when no h1."""
        section = FacetExtractor.extract_section('string — Common string operations', [])
        self.assertEqual(section, 'string')
    
    def test_extract_section_default(self):
        """Should return 'general' when no section found."""
        section = FacetExtractor.extract_section('', [])
        self.assertEqual(section, 'general')
    
    def test_extract_doc_type_from_url(self):
        """Should detect document type from URL."""
        test_cases = [
            ('https://docs.python.org/3/tutorial/classes.html', 'tutorial'),
            ('https://docs.python.org/3/library/string.html', 'library'),
            ('https://docs.python.org/3/reference/datamodel.html', 'reference'),
            ('https://docs.python.org/3/howto/logging.html', 'howto'),
            ('https://docs.python.org/3/faq/general.html', 'faq'),
            ('https://docs.example.com/api/users', 'api'),
        ]
        
        for url, expected_type in test_cases:
            result = FacetExtractor.extract_doc_type(url)
            self.assertEqual(result, expected_type, f"URL: {url}")
    
    def test_extract_doc_type_from_title(self):
        """Should detect document type from title."""
        result = FacetExtractor.extract_doc_type(
            'https://example.com/page', 
            'Python Tutorial: Getting Started'
        )
        self.assertEqual(result, 'tutorial')
    
    def test_extract_doc_type_default(self):
        """Should return 'documentation' when type unknown."""
        result = FacetExtractor.extract_doc_type('https://example.com/page')
        self.assertEqual(result, 'documentation')
    
    def test_extract_path_facets(self):
        """Should extract path components as facets."""
        facets = FacetExtractor.extract_path_facets(
            'https://docs.python.org/3/library/string.html'
        )
        self.assertIn('library', facets)
        self.assertIn('string', facets)
    
    def test_extract_path_facets_skips_version(self):
        """Should skip version numbers in path."""
        facets = FacetExtractor.extract_path_facets(
            'https://docs.python.org/3.11/library/string.html'
        )
        self.assertNotIn('3.11', facets)
        self.assertIn('library', facets)
    
    def test_extract_path_facets_limit_depth(self):
        """Should limit facet depth to 3."""
        facets = FacetExtractor.extract_path_facets(
            'https://example.com/a/b/c/d/e/f.html'
        )
        self.assertLessEqual(len(facets), 3)


class TestFacetIndex(unittest.TestCase):
    """Test FacetIndex class."""
    
    def setUp(self):
        """Create a facet index with test data."""
        self.index = FacetIndex()
        
        # Add test documents
        self.index.add_document(
            doc_id=1,
            url='https://docs.python.org/3/tutorial/classes.html',
            title='Classes — Python tutorial',
            headings=[(1, 'Classes')]
        )
        
        self.index.add_document(
            doc_id=2,
            url='https://docs.python.org/3/library/string.html',
            title='string — Common string operations',
            headings=[(1, 'string')]
        )
        
        self.index.add_document(
            doc_id=3,
            url='https://docs.python.org/3/library/os.html',
            title='os — Operating system interfaces',
            headings=[(1, 'os')]
        )
        
        self.index.add_document(
            doc_id=4,
            url='https://docs.python.org/3/tutorial/datastructures.html',
            title='Data Structures — Python tutorial',
            headings=[(1, 'Data Structures')]
        )
    
    def test_get_facet_values(self):
        """Should return facet values with counts."""
        values = self.index.get_facet_values('type')
        self.assertIn('tutorial', values)
        self.assertIn('library', values)
        self.assertEqual(values['tutorial'], 2)  # docs 1 and 4
        self.assertEqual(values['library'], 2)  # docs 2 and 3
    
    def test_get_facet_counts(self):
        """Should get facet counts for a set of documents."""
        doc_ids = {1, 2, 3}
        counts = self.index.get_facet_counts(doc_ids)
        
        self.assertIn('type', counts)
        self.assertEqual(counts['type']['tutorial'], 1)
        self.assertEqual(counts['type']['library'], 2)
    
    def test_filter_by_facet(self):
        """Should filter documents by facet value."""
        all_docs = {1, 2, 3, 4}
        
        # Filter by type=tutorial
        tutorials = self.index.filter_by_facet(all_docs, 'type', 'tutorial')
        self.assertEqual(tutorials, {1, 4})
        
        # Filter by type=library
        libraries = self.index.filter_by_facet(all_docs, 'type', 'library')
        self.assertEqual(libraries, {2, 3})
    
    def test_filter_by_facets_multiple(self):
        """Should filter by multiple facets (AND logic)."""
        all_docs = {1, 2, 3, 4}
        
        # This will filter by type and category (if available)
        filters = {'type': 'library', 'category': 'library'}
        result = self.index.filter_by_facets(all_docs, filters)
        
        # Should only return library docs
        self.assertTrue(result.issubset({2, 3}))
    
    def test_filter_nonexistent_facet(self):
        """Filtering by nonexistent value should return empty."""
        all_docs = {1, 2, 3, 4}
        result = self.index.filter_by_facet(all_docs, 'type', 'nonexistent')
        self.assertEqual(result, set())
    
    def test_get_doc_facets(self):
        """Should return facets for a specific document."""
        facets = self.index.get_doc_facets(1)
        self.assertIn('section', facets)
        self.assertIn('type', facets)
        self.assertEqual(facets['type'], 'tutorial')
    
    def test_get_all_facet_types(self):
        """Should return all facet types."""
        types = self.index.get_all_facet_types()
        self.assertIn('section', types)
        self.assertIn('type', types)
        self.assertIn('category', types)
    
    def test_serialization(self):
        """Should serialize and deserialize correctly."""
        # Serialize
        data = self.index.to_dict()
        
        # Deserialize
        restored = FacetIndex.from_dict(data)
        
        # Verify
        self.assertEqual(
            self.index.get_facet_values('type'),
            restored.get_facet_values('type')
        )
        self.assertEqual(
            self.index.get_doc_facets(1),
            restored.get_doc_facets(1)
        )
    
    def test_get_stats(self):
        """Should return statistics."""
        stats = self.index.get_stats()
        self.assertEqual(stats['total_documents'], 4)
        self.assertIn('facets', stats)


class TestFacetIndexEdgeCases(unittest.TestCase):
    """Test edge cases for FacetIndex."""
    
    def test_empty_index(self):
        """Should handle empty index."""
        index = FacetIndex()
        
        self.assertEqual(index.get_facet_values('type'), {})
        self.assertEqual(index.get_facet_counts(set()), {})
        self.assertEqual(index.get_doc_facets(1), {})
    
    def test_filter_empty_doc_set(self):
        """Filtering empty set should return empty set."""
        index = FacetIndex()
        result = index.filter_by_facet(set(), 'type', 'tutorial')
        self.assertEqual(result, set())
    
    def test_document_with_no_headings(self):
        """Should handle document with no headings."""
        index = FacetIndex()
        index.add_document(
            doc_id=1,
            url='https://example.com/page',
            title='Simple Page'
        )
        
        facets = index.get_doc_facets(1)
        self.assertIn('section', facets)
        self.assertIn('type', facets)


if __name__ == '__main__':
    unittest.main()
