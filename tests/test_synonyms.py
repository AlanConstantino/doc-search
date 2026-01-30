"""
Tests for synonym expansion functionality.
"""

import unittest
from doc_search.synonyms import SynonymExpander, QueryExpander


class TestSynonymExpander(unittest.TestCase):
    """Test SynonymExpander class."""
    
    def test_add_synonym_group(self):
        """Should add synonym group correctly."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'cat', 'feline', 'kitty'})
        
        synonyms = exp.get_synonyms('cat')
        self.assertIn('cat', synonyms)
        self.assertIn('feline', synonyms)
        self.assertIn('kitty', synonyms)
    
    def test_add_synonym_pair(self):
        """Should add synonym pair correctly."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_pair('big', 'large')
        
        self.assertIn('large', exp.get_synonyms('big'))
        self.assertIn('big', exp.get_synonyms('large'))
    
    def test_case_insensitive(self):
        """Should handle case insensitively."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'Hello', 'Hi', 'Greetings'})
        
        synonyms = exp.get_synonyms('HELLO')
        self.assertIn('hello', synonyms)
        self.assertIn('hi', synonyms)
    
    def test_get_synonyms_include_self(self):
        """Should optionally include the term itself."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'a', 'b'})
        
        with_self = exp.get_synonyms('a', include_self=True)
        without_self = exp.get_synonyms('a', include_self=False)
        
        self.assertIn('a', with_self)
        self.assertNotIn('a', without_self)
        self.assertIn('b', without_self)
    
    def test_unknown_term(self):
        """Unknown term should return only itself (or empty)."""
        exp = SynonymExpander(include_defaults=False)
        
        with_self = exp.get_synonyms('unknown', include_self=True)
        without_self = exp.get_synonyms('unknown', include_self=False)
        
        self.assertEqual(with_self, {'unknown'})
        self.assertEqual(without_self, set())
    
    def test_expand_terms(self):
        """Should expand terms with synonyms."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'function', 'method', 'procedure'})
        
        expanded = exp.expand_terms(['function', 'call'])
        
        self.assertIn('function', expanded)
        self.assertIn('call', expanded)
        # At least one synonym should be added
        self.assertTrue(
            'method' in expanded or 'procedure' in expanded
        )
    
    def test_expand_terms_no_duplicates(self):
        """Expansion should not produce duplicates."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'a', 'b'})
        
        expanded = exp.expand_terms(['a', 'a', 'b'])
        
        # Check no duplicates
        self.assertEqual(len(expanded), len(set(expanded)))
    
    def test_expand_query_with_boost(self):
        """Should return terms with boost weights."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'function', 'method'})
        
        result = exp.expand_query(['function'], boost_original=2.0)
        
        # Original should have higher boost
        orig_boost = next(b for t, b in result if t == 'function')
        syn_boost = next(b for t, b in result if t == 'method')
        
        self.assertEqual(orig_boost, 2.0)
        self.assertEqual(syn_boost, 1.0)
    
    def test_has_synonyms(self):
        """Should check if term has synonyms."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'a', 'b'})
        
        self.assertTrue(exp.has_synonyms('a'))
        self.assertFalse(exp.has_synonyms('unknown'))
    
    def test_merge_synonym_groups(self):
        """Adding overlapping groups should merge them."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'a', 'b'})
        exp.add_synonym_group({'b', 'c'})
        
        # All should be synonyms now
        synonyms = exp.get_synonyms('a')
        self.assertIn('a', synonyms)
        self.assertIn('b', synonyms)
        self.assertIn('c', synonyms)


class TestSynonymExpanderDefaults(unittest.TestCase):
    """Test built-in default synonyms."""
    
    def test_default_synonyms_loaded(self):
        """Default synonyms should be loaded."""
        exp = SynonymExpander(include_defaults=True)
        
        # Check some expected defaults
        self.assertIn('method', exp.get_synonyms('function'))
        self.assertIn('array', exp.get_synonyms('list'))
        self.assertIn('dict', exp.get_synonyms('dictionary'))
    
    def test_programming_terms(self):
        """Should have programming-related synonyms."""
        exp = SynonymExpander()
        
        # Variables
        self.assertTrue(exp.has_synonyms('variable'))
        self.assertIn('var', exp.get_synonyms('variable'))
        
        # Data types
        self.assertTrue(exp.has_synonyms('string'))
        self.assertIn('str', exp.get_synonyms('string'))
        
        # Operations
        self.assertTrue(exp.has_synonyms('create'))
        self.assertIn('make', exp.get_synonyms('create'))


class TestSynonymExpanderSerialization(unittest.TestCase):
    """Test serialization/deserialization."""
    
    def test_to_dict(self):
        """Should serialize to dictionary."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'a', 'b', 'c'})
        
        data = exp.to_dict()
        
        self.assertIn('groups', data)
        self.assertEqual(len(data['groups']), 1)
    
    def test_from_dict(self):
        """Should deserialize from dictionary."""
        data = {'groups': [['a', 'b', 'c'], ['x', 'y']]}
        
        exp = SynonymExpander.from_dict(data, include_defaults=False)
        
        self.assertIn('b', exp.get_synonyms('a'))
        self.assertIn('y', exp.get_synonyms('x'))
    
    def test_round_trip(self):
        """Should survive serialization round trip."""
        exp1 = SynonymExpander(include_defaults=False)
        exp1.add_synonym_group({'cat', 'feline'})
        exp1.add_synonym_group({'dog', 'canine'})
        
        data = exp1.to_dict()
        exp2 = SynonymExpander.from_dict(data, include_defaults=False)
        
        self.assertEqual(
            exp1.get_synonyms('cat'),
            exp2.get_synonyms('cat')
        )
        self.assertEqual(
            exp1.get_synonyms('dog'),
            exp2.get_synonyms('dog')
        )


class TestQueryExpander(unittest.TestCase):
    """Test QueryExpander class."""
    
    def test_expand_basic(self):
        """Should expand query terms."""
        exp = QueryExpander(
            SynonymExpander(include_defaults=False),
            use_stemming=False
        )
        exp.synonyms.add_synonym_group({'search', 'find', 'lookup'})
        
        result = exp.expand(['search', 'term'])
        
        self.assertIn('search', result)
        self.assertIn('term', result)
        # At least one synonym should be present
        self.assertTrue('find' in result or 'lookup' in result)
    
    def test_expand_without_original(self):
        """Should optionally exclude original terms."""
        exp = QueryExpander(
            SynonymExpander(include_defaults=False),
            use_stemming=False
        )
        exp.synonyms.add_synonym_group({'a', 'b'})
        
        result = exp.expand(['a'], include_original=False)
        
        # Original 'a' should not be included
        # But we need at least the synonym
        self.assertIn('b', result)
    
    def test_max_synonyms_limit(self):
        """Should respect max_synonyms limit."""
        exp = QueryExpander(
            SynonymExpander(include_defaults=False),
            use_stemming=False
        )
        exp.synonyms.add_synonym_group({'a', 'b', 'c', 'd', 'e'})
        
        result = exp.expand(['a'], max_synonyms=2)
        
        # Original + max 2 synonyms = at most 3 terms
        self.assertLessEqual(len(result), 3)


class TestSynonymExpanderEdgeCases(unittest.TestCase):
    """Test edge cases."""
    
    def test_empty_group(self):
        """Should handle empty synonym group."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group(set())  # Empty set
        
        # Should not crash
        self.assertEqual(exp.get_synonyms('test'), {'test'})
    
    def test_single_term_group(self):
        """Single term group is valid but has no synonyms."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'alone'})
        
        # Has entry but no other synonyms
        synonyms = exp.get_synonyms('alone', include_self=False)
        self.assertEqual(synonyms, set())
    
    def test_empty_term(self):
        """Should handle empty string term."""
        exp = SynonymExpander(include_defaults=False)
        exp.add_synonym_group({'', 'empty'})
        
        # Empty string should be filtered out
        synonyms = exp.get_synonyms('empty')
        self.assertNotIn('', synonyms)


if __name__ == '__main__':
    unittest.main()
