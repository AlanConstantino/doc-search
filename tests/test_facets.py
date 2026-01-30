"""
Tests for faceted search functionality.

Facets are domain-agnostic: extracted from URL path structure,
not hardcoded patterns.
"""

import unittest
from doc_search.facets import FacetExtractor, FacetIndex


class TestFacetExtractor(unittest.TestCase):
    """Test facet extraction logic."""
    
    def test_extract_section_from_title_with_separator(self):
        """Should extract section from title with separator."""
        section = FacetExtractor.extract_section('string — Common string operations', [])
        self.assertEqual(section, 'string')
    
    def test_extract_section_from_title_colon(self):
        """Should handle colon separator."""
        section = FacetExtractor.extract_section('API Reference: Users', [])
        self.assertEqual(section, 'api reference')
    
    def test_extract_section_from_title_pipe(self):
        """Should handle pipe separator."""
        section = FacetExtractor.extract_section('Getting Started | Documentation', [])
        self.assertEqual(section, 'getting started')
    
    def test_extract_section_simple_title(self):
        """Should handle simple title without separator."""
        section = FacetExtractor.extract_section('Installation Guide', [])
        self.assertIn('installation', section)
    
    def test_extract_section_default(self):
        """Should return 'general' when no section found."""
        section = FacetExtractor.extract_section('', [])
        self.assertEqual(section, 'general')
    
    def test_extract_path_facets(self):
        """Should extract path components as facets."""
        facets = FacetExtractor.extract_path_facets(
            'https://docs.example.com/guide/getting-started/install.html'
        )
        self.assertIn('guide', facets)
        self.assertIn('getting-started', facets)
    
    def test_extract_path_facets_skips_version(self):
        """Should skip version numbers in path."""
        facets = FacetExtractor.extract_path_facets(
            'https://docs.python.org/3.11/library/string.html'
        )
        self.assertNotIn('3.11', facets)
        self.assertIn('library', facets)
    
    def test_extract_path_facets_skips_generic(self):
        """Should skip generic parts like 'docs', 'en'."""
        facets = FacetExtractor.extract_path_facets(
            'https://example.com/docs/en/api/users.html'
        )
        self.assertNotIn('docs', facets)
        self.assertNotIn('en', facets)
        self.assertIn('api', facets)
        self.assertIn('users', facets)
    
    def test_extract_path_facets_limit_depth(self):
        """Should limit facet depth to 3."""
        facets = FacetExtractor.extract_path_facets(
            'https://example.com/a/b/c/d/e/f.html'
        )
        self.assertLessEqual(len(facets), 3)
    
    def test_extract_path_facets_removes_extension(self):
        """Should remove file extensions."""
        facets = FacetExtractor.extract_path_facets(
            'https://example.com/guide/install.html'
        )
        self.assertIn('install', facets)
        self.assertNotIn('install.html', facets)


class TestFacetIndex(unittest.TestCase):
    """Test FacetIndex class."""
    
    def setUp(self):
        """Create a facet index with test data."""
        self.index = FacetIndex()
        
        # Add test documents with various URL structures
        self.index.add_document(
            doc_id=1,
            url='https://docs.example.com/tutorial/basics.html',
            title='Basics — Tutorial',
        )
        
        self.index.add_document(
            doc_id=2,
            url='https://docs.example.com/reference/api.html',
            title='API Reference',
        )
        
        self.index.add_document(
            doc_id=3,
            url='https://docs.example.com/reference/config.html',
            title='Configuration Reference',
        )
        
        self.index.add_document(
            doc_id=4,
            url='https://docs.example.com/tutorial/advanced.html',
            title='Advanced — Tutorial',
        )
    
    def test_get_facet_values_category(self):
        """Should return category facet values with counts."""
        values = self.index.get_facet_values('category')
        self.assertIn('tutorial', values)
        self.assertIn('reference', values)
        self.assertEqual(values['tutorial'], 2)  # docs 1 and 4
        self.assertEqual(values['reference'], 2)  # docs 2 and 3
    
    def test_get_facet_counts(self):
        """Should get facet counts for a set of documents."""
        doc_ids = {1, 2, 3}
        counts = self.index.get_facet_counts(doc_ids)
        
        self.assertIn('category', counts)
        self.assertEqual(counts['category']['tutorial'], 1)
        self.assertEqual(counts['category']['reference'], 2)
    
    def test_filter_by_category(self):
        """Should filter documents by category."""
        all_docs = {1, 2, 3, 4}
        
        # Filter by category=tutorial
        tutorials = self.index.filter_by_facet(all_docs, 'category', 'tutorial')
        self.assertEqual(tutorials, {1, 4})
        
        # Filter by category=reference
        references = self.index.filter_by_facet(all_docs, 'category', 'reference')
        self.assertEqual(references, {2, 3})
    
    def test_filter_by_facets_multiple(self):
        """Should filter by multiple facets (AND logic)."""
        all_docs = {1, 2, 3, 4}
        
        filters = {'category': 'reference', 'subcategory': 'api'}
        result = self.index.filter_by_facets(all_docs, filters)
        
        # Should only return doc 2 (reference/api)
        self.assertEqual(result, {2})
    
    def test_filter_nonexistent_facet(self):
        """Filtering by nonexistent value should return empty."""
        all_docs = {1, 2, 3, 4}
        result = self.index.filter_by_facet(all_docs, 'category', 'nonexistent')
        self.assertEqual(result, set())
    
    def test_get_doc_facets(self):
        """Should return facets for a specific document."""
        facets = self.index.get_doc_facets(1)
        self.assertIn('section', facets)
        self.assertIn('category', facets)
        self.assertEqual(facets['category'], 'tutorial')
    
    def test_get_all_facet_types(self):
        """Should return all facet types."""
        types = self.index.get_all_facet_types()
        self.assertIn('section', types)
        self.assertIn('category', types)
    
    def test_serialization(self):
        """Should serialize and deserialize correctly."""
        # Serialize
        data = self.index.to_dict()
        
        # Deserialize
        restored = FacetIndex.from_dict(data)
        
        # Verify
        self.assertEqual(
            self.index.get_facet_values('category'),
            restored.get_facet_values('category')
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
        
        self.assertEqual(index.get_facet_values('category'), {})
        self.assertEqual(index.get_facet_counts(set()), {})
        self.assertEqual(index.get_doc_facets(1), {})
    
    def test_filter_empty_doc_set(self):
        """Filtering empty set should return empty set."""
        index = FacetIndex()
        result = index.filter_by_facet(set(), 'category', 'tutorial')
        self.assertEqual(result, set())
    
    def test_document_with_no_path(self):
        """Should handle document with minimal URL path."""
        index = FacetIndex()
        index.add_document(
            doc_id=1,
            url='https://example.com/',
            title='Home Page'
        )
        
        facets = index.get_doc_facets(1)
        self.assertIn('section', facets)
    
    def test_document_deep_path(self):
        """Should handle document with deep URL path."""
        index = FacetIndex()
        index.add_document(
            doc_id=1,
            url='https://example.com/docs/api/v2/users/create.html',
            title='Create User'
        )
        
        facets = index.get_doc_facets(1)
        self.assertIn('category', facets)
        # Should have category from first meaningful path segment
        self.assertIn(facets.get('category'), ['api', 'v2', 'users'])


class TestDomainAgnostic(unittest.TestCase):
    """Test that facets work across different documentation styles."""
    
    def test_python_docs_style(self):
        """Should work with Python docs URL structure."""
        index = FacetIndex()
        index.add_document(
            doc_id=1,
            url='https://docs.python.org/3/library/json.html',
            title='json — JSON encoder and decoder'
        )
        
        facets = index.get_doc_facets(1)
        self.assertEqual(facets.get('category'), 'library')
        self.assertEqual(facets.get('section'), 'json')
    
    def test_readthedocs_style(self):
        """Should work with ReadTheDocs URL structure."""
        index = FacetIndex()
        index.add_document(
            doc_id=1,
            url='https://myproject.readthedocs.io/en/latest/quickstart.html',
            title='Quickstart Guide'
        )
        
        facets = index.get_doc_facets(1)
        # Should extract meaningful category
        self.assertIn('category', facets)
    
    def test_docusaurus_style(self):
        """Should work with Docusaurus URL structure."""
        index = FacetIndex()
        index.add_document(
            doc_id=1,
            url='https://example.com/docs/intro',
            title='Introduction'
        )
        
        facets = index.get_doc_facets(1)
        self.assertIn('category', facets)
    
    def test_generic_corporate_docs(self):
        """Should work with generic corporate documentation."""
        index = FacetIndex()
        index.add_document(
            doc_id=1,
            url='https://company.com/help/articles/getting-started',
            title='Getting Started'
        )
        
        facets = index.get_doc_facets(1)
        self.assertIn('category', facets)


if __name__ == '__main__':
    unittest.main()
