"""
Tests for spell checking and suggestions.
"""

import unittest
from doc_search.spellcheck import (
    levenshtein_distance,
    damerau_levenshtein_distance,
    SpellChecker
)


class TestLevenshteinDistance(unittest.TestCase):
    """Test Levenshtein distance calculation."""
    
    def test_identical_strings(self):
        """Identical strings have distance 0."""
        self.assertEqual(levenshtein_distance('hello', 'hello'), 0)
        self.assertEqual(levenshtein_distance('', ''), 0)
    
    def test_empty_string(self):
        """Distance to/from empty string is length of other string."""
        self.assertEqual(levenshtein_distance('', 'abc'), 3)
        self.assertEqual(levenshtein_distance('abc', ''), 3)
    
    def test_single_insertion(self):
        """Single character insertion."""
        self.assertEqual(levenshtein_distance('cat', 'cats'), 1)
        self.assertEqual(levenshtein_distance('at', 'cat'), 1)
    
    def test_single_deletion(self):
        """Single character deletion."""
        self.assertEqual(levenshtein_distance('cats', 'cat'), 1)
        self.assertEqual(levenshtein_distance('hello', 'helo'), 1)
    
    def test_single_substitution(self):
        """Single character substitution."""
        self.assertEqual(levenshtein_distance('cat', 'bat'), 1)
        self.assertEqual(levenshtein_distance('hello', 'hallo'), 1)
    
    def test_multiple_edits(self):
        """Multiple edits required."""
        self.assertEqual(levenshtein_distance('kitten', 'sitting'), 3)
        self.assertEqual(levenshtein_distance('saturday', 'sunday'), 3)
    
    def test_symmetric(self):
        """Distance should be symmetric."""
        self.assertEqual(
            levenshtein_distance('abc', 'def'),
            levenshtein_distance('def', 'abc')
        )


class TestDamerauLevenshteinDistance(unittest.TestCase):
    """Test Damerau-Levenshtein distance (with transpositions)."""
    
    def test_transposition(self):
        """Adjacent transposition should be 1 edit."""
        self.assertEqual(damerau_levenshtein_distance('ab', 'ba'), 1)
        self.assertEqual(damerau_levenshtein_distance('teh', 'the'), 1)
        self.assertEqual(damerau_levenshtein_distance('recieve', 'receive'), 1)
    
    def test_regular_levenshtein_cases(self):
        """Should still handle regular cases."""
        self.assertEqual(damerau_levenshtein_distance('hello', 'hello'), 0)
        self.assertEqual(damerau_levenshtein_distance('cat', 'cats'), 1)
        self.assertEqual(damerau_levenshtein_distance('cat', 'bat'), 1)
    
    def test_multiple_transpositions(self):
        """Multiple transpositions."""
        # 'abcd' -> 'badc' requires 2 transpositions
        self.assertEqual(damerau_levenshtein_distance('abcd', 'badc'), 2)


class TestSpellChecker(unittest.TestCase):
    """Test SpellChecker class."""
    
    def setUp(self):
        """Create a spell checker with test vocabulary."""
        self.vocab = {
            'python', 'programming', 'function', 'class', 'method',
            'variable', 'string', 'integer', 'list', 'dictionary',
            'tuple', 'set', 'loop', 'while', 'for', 'if', 'else',
            'return', 'import', 'from', 'module', 'package',
            'exception', 'error', 'debug', 'print', 'input',
            'file', 'read', 'write', 'open', 'close', 'async',
            'await', 'generator', 'iterator', 'decorator',
            'comprehension', 'lambda', 'filter', 'map', 'reduce'
        }
        self.checker = SpellChecker(self.vocab, max_distance=2)
    
    def test_valid_word(self):
        """Valid words should return no suggestions."""
        self.assertTrue(self.checker.is_valid('python'))
        self.assertEqual(self.checker.suggest('python'), [])
    
    def test_case_insensitive(self):
        """Validation should be case insensitive."""
        self.assertTrue(self.checker.is_valid('Python'))
        self.assertTrue(self.checker.is_valid('PYTHON'))
    
    def test_single_typo(self):
        """Should suggest correction for single typo."""
        suggestions = self.checker.suggest('pyhton')  # common typo
        self.assertTrue(len(suggestions) > 0)
        # First suggestion should be 'python'
        self.assertEqual(suggestions[0][0], 'python')
        self.assertEqual(suggestions[0][1], 1)  # distance 1
    
    def test_transposition_typo(self):
        """Should handle transposition typos."""
        suggestions = self.checker.suggest('stirng')  # string with i-r swapped
        found_string = any(s[0] == 'string' for s in suggestions)
        self.assertTrue(found_string)
    
    def test_missing_letter(self):
        """Should suggest for missing letter."""
        suggestions = self.checker.suggest('imprt')  # missing 'o'
        found_import = any(s[0] == 'import' for s in suggestions)
        self.assertTrue(found_import)
    
    def test_extra_letter(self):
        """Should suggest for extra letter."""
        suggestions = self.checker.suggest('prrint')  # extra 'r'
        found_print = any(s[0] == 'print' for s in suggestions)
        self.assertTrue(found_print)
    
    def test_no_suggestion_for_very_different(self):
        """Words too different should get no suggestions."""
        suggestions = self.checker.suggest('xyz')
        self.assertEqual(len(suggestions), 0)
    
    def test_max_suggestions(self):
        """Should respect max_suggestions limit."""
        # 'srt' could match 'set', might match others
        suggestions = self.checker.suggest('srt', max_suggestions=2)
        self.assertLessEqual(len(suggestions), 2)
    
    def test_suggest_query(self):
        """Should suggest corrections for query terms."""
        result = self.checker.suggest_query(['pyhton', 'functoin'])
        self.assertIsNotNone(result)
        corrected_terms, suggestion_str = result
        self.assertEqual(corrected_terms, ['python', 'function'])
        self.assertEqual(suggestion_str, 'python function')
    
    def test_suggest_query_no_correction(self):
        """Should return None when no correction needed."""
        result = self.checker.suggest_query(['python', 'function'])
        self.assertIsNone(result)
    
    def test_suggest_query_partial_correction(self):
        """Should correct only invalid terms."""
        result = self.checker.suggest_query(['python', 'functoin'])
        self.assertIsNotNone(result)
        corrected_terms, _ = result
        self.assertEqual(corrected_terms, ['python', 'function'])
    
    def test_vocabulary_size(self):
        """Should report correct vocabulary size."""
        self.assertEqual(self.checker.get_vocabulary_size(), len(self.vocab))


class TestSpellCheckerEdgeCases(unittest.TestCase):
    """Test edge cases for SpellChecker."""
    
    def test_empty_vocabulary(self):
        """Should handle empty vocabulary."""
        checker = SpellChecker(set())
        self.assertFalse(checker.is_valid('hello'))
        self.assertEqual(checker.suggest('hello'), [])
    
    def test_single_word_vocabulary(self):
        """Should work with single word vocabulary."""
        checker = SpellChecker({'hello'})
        self.assertTrue(checker.is_valid('hello'))
        suggestions = checker.suggest('helo')
        self.assertEqual(suggestions[0][0], 'hello')
    
    def test_short_words(self):
        """Should handle short words correctly."""
        checker = SpellChecker({'a', 'an', 'if', 'is', 'in', 'it'})
        self.assertTrue(checker.is_valid('if'))
        suggestions = checker.suggest('ix')
        # Should suggest 'if', 'is', 'in', 'it'
        self.assertTrue(len(suggestions) > 0)


if __name__ == '__main__':
    unittest.main()
