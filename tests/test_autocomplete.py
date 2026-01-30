"""
Tests for autocomplete functionality.
"""

import unittest
from doc_search.autocomplete import Autocomplete, MultiWordAutocomplete


class TestAutocomplete(unittest.TestCase):
    """Test single-word autocomplete."""
    
    def setUp(self):
        """Create autocomplete with test data."""
        self.ac = Autocomplete()
        words = [
            'python', 'programming', 'program', 'print', 'process',
            'function', 'file', 'filter', 'for', 'from',
            'class', 'class_method', 'classmethod', 'close',
            'list', 'lambda', 'loop'
        ]
        # Add with varying frequencies
        frequencies = {
            'python': 100,
            'print': 80,
            'function': 70,
            'list': 60,
            'class': 50,
            'for': 40,
            'from': 30,
        }
        self.ac.add_words(words, frequencies)
    
    def test_exact_prefix_match(self):
        """Should return words starting with prefix."""
        suggestions = self.ac.suggest('pro')
        self.assertIn('programming', suggestions)
        self.assertIn('program', suggestions)
        self.assertIn('process', suggestions)
    
    def test_single_char_prefix(self):
        """Should work with single character prefix."""
        suggestions = self.ac.suggest('p')
        self.assertTrue(len(suggestions) > 0)
        self.assertTrue(all(s.startswith('p') for s in suggestions))
    
    def test_case_insensitive(self):
        """Should be case insensitive."""
        lower = self.ac.suggest('py')
        upper = self.ac.suggest('PY')
        mixed = self.ac.suggest('Py')
        self.assertEqual(lower, upper)
        self.assertEqual(lower, mixed)
    
    def test_no_match(self):
        """Should return empty list for non-matching prefix."""
        suggestions = self.ac.suggest('xyz')
        self.assertEqual(suggestions, [])
    
    def test_empty_prefix(self):
        """Should return empty list for empty prefix."""
        suggestions = self.ac.suggest('')
        self.assertEqual(suggestions, [])
    
    def test_exact_word(self):
        """Prefix that is exact word should include that word."""
        suggestions = self.ac.suggest('print')
        self.assertIn('print', suggestions)
    
    def test_frequency_ordering(self):
        """Higher frequency words should appear first."""
        suggestions = self.ac.suggest('p')
        # 'python' has highest frequency, should be first
        self.assertEqual(suggestions[0], 'python')
        # 'print' should be second
        self.assertEqual(suggestions[1], 'print')
    
    def test_max_suggestions(self):
        """Should respect max_suggestions limit."""
        suggestions = self.ac.suggest('p', max_suggestions=3)
        self.assertLessEqual(len(suggestions), 3)
    
    def test_suggest_with_scores(self):
        """Should return scores with suggestions."""
        results = self.ac.suggest_with_scores('py')
        self.assertTrue(len(results) > 0)
        word, freq = results[0]
        self.assertEqual(word, 'python')
        self.assertEqual(freq, 100)
    
    def test_has_prefix(self):
        """Should check if prefix exists."""
        self.assertTrue(self.ac.has_prefix('py'))
        self.assertTrue(self.ac.has_prefix('python'))
        self.assertFalse(self.ac.has_prefix('xyz'))
    
    def test_contains(self):
        """Should check if exact word exists."""
        self.assertTrue(self.ac.contains('python'))
        self.assertFalse(self.ac.contains('py'))  # prefix but not a word
        self.assertFalse(self.ac.contains('pythons'))
    
    def test_word_count(self):
        """Should track word count correctly."""
        ac = Autocomplete()
        self.assertEqual(ac.get_word_count(), 0)
        ac.add_word('hello')
        self.assertEqual(ac.get_word_count(), 1)
        ac.add_word('hello')  # duplicate
        self.assertEqual(ac.get_word_count(), 1)
        ac.add_word('world')
        self.assertEqual(ac.get_word_count(), 2)
    
    def test_get_frequency(self):
        """Should return correct frequency."""
        self.assertEqual(self.ac.get_frequency('python'), 100)
        self.assertEqual(self.ac.get_frequency('function'), 70)
        self.assertEqual(self.ac.get_frequency('xyz'), 0)
    
    def test_frequency_accumulates(self):
        """Adding same word multiple times should accumulate frequency."""
        ac = Autocomplete()
        ac.add_word('test', 10)
        ac.add_word('test', 5)
        self.assertEqual(ac.get_frequency('test'), 15)


class TestAutocompleteFromIndex(unittest.TestCase):
    """Test building autocomplete from index."""
    
    def test_build_from_index(self):
        """Should build from term -> doc_freq mapping."""
        index = {
            'python': 50,
            'programming': 30,
            'print': 20,
        }
        ac = Autocomplete()
        ac.build_from_index(index)
        
        self.assertEqual(ac.get_word_count(), 3)
        suggestions = ac.suggest('p')
        # python should be first (highest doc freq)
        self.assertEqual(suggestions[0], 'python')


class TestMultiWordAutocomplete(unittest.TestCase):
    """Test multi-word query autocomplete."""
    
    def setUp(self):
        """Create multi-word autocomplete."""
        ac = Autocomplete()
        ac.add_words([
            'python', 'programming', 'print',
            'list', 'lambda', 'loop',
            'comprehension', 'class'
        ])
        self.mwac = MultiWordAutocomplete(ac)
    
    def test_single_word(self):
        """Single word should work like regular autocomplete."""
        suggestions = self.mwac.suggest('py')
        self.assertIn('python', suggestions)
    
    def test_multi_word(self):
        """Should complete last word only."""
        suggestions = self.mwac.suggest('python li')
        # 'li' prefix matches 'list'
        self.assertIn('python list', suggestions)
        # All suggestions should start with 'python '
        self.assertTrue(all(s.startswith('python ') for s in suggestions))
    
    def test_preserves_previous_words(self):
        """Previous words should be preserved exactly."""
        suggestions = self.mwac.suggest('hello world py')
        self.assertTrue(all(s.startswith('hello world ') for s in suggestions))
    
    def test_empty_current_word(self):
        """Trailing space with no partial word should return empty."""
        suggestions = self.mwac.suggest('python ')
        self.assertEqual(suggestions, [])
    
    def test_empty_query(self):
        """Empty query should return empty list."""
        suggestions = self.mwac.suggest('')
        self.assertEqual(suggestions, [])


class TestAutocompleteEdgeCases(unittest.TestCase):
    """Test edge cases."""
    
    def test_special_characters_in_prefix(self):
        """Should handle prefix with special chars."""
        ac = Autocomplete()
        ac.add_word('__init__')
        ac.add_word('_private')
        
        suggestions = ac.suggest('_')
        self.assertIn('__init__', suggestions)
        self.assertIn('_private', suggestions)
    
    def test_numeric_prefix(self):
        """Should handle numeric prefixes."""
        ac = Autocomplete()
        ac.add_word('123abc')
        ac.add_word('123xyz')
        
        suggestions = ac.suggest('123')
        self.assertEqual(len(suggestions), 2)
    
    def test_unicode(self):
        """Should handle unicode characters."""
        ac = Autocomplete()
        ac.add_word('café')
        ac.add_word('naïve')
        
        suggestions = ac.suggest('ca')
        self.assertIn('café', suggestions)
    
    def test_very_long_words(self):
        """Should handle very long words."""
        ac = Autocomplete()
        long_word = 'supercalifragilisticexpialidocious'
        ac.add_word(long_word)
        
        suggestions = ac.suggest('supercali')
        self.assertIn(long_word, suggestions)


if __name__ == '__main__':
    unittest.main()
