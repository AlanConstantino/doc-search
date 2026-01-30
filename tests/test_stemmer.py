"""
Tests for the Porter Stemmer implementation.
"""

import unittest
from doc_search.stemmer import stem, stem_tokens


class TestPorterStemmer(unittest.TestCase):
    """Test cases for the Porter Stemmer algorithm."""
    
    def test_step1a_plurals(self):
        """Step 1a: Handle plurals."""
        self.assertEqual(stem('caresses'), 'caress')
        self.assertEqual(stem('ponies'), 'poni')
        self.assertEqual(stem('ties'), 'ti')
        self.assertEqual(stem('caress'), 'caress')
        self.assertEqual(stem('cats'), 'cat')
    
    def test_step1b_past_tense(self):
        """Step 1b: Handle past tense and -ing."""
        self.assertEqual(stem('agreed'), 'agre')
        self.assertEqual(stem('plastered'), 'plaster')
        self.assertEqual(stem('bled'), 'bled')
        self.assertEqual(stem('motoring'), 'motor')
        self.assertEqual(stem('sing'), 'sing')
    
    def test_step1b_special_endings(self):
        """Step 1b: Special endings after removing -ed/-ing."""
        self.assertEqual(stem('conflated'), 'conflat')
        self.assertEqual(stem('troubled'), 'troubl')
        self.assertEqual(stem('sized'), 'size')
        self.assertEqual(stem('hopping'), 'hop')
        self.assertEqual(stem('tanned'), 'tan')
        self.assertEqual(stem('falling'), 'fall')
        self.assertEqual(stem('failing'), 'fail')
        self.assertEqual(stem('filing'), 'file')
    
    def test_step1c_y_to_i(self):
        """Step 1c: Terminal y to i."""
        self.assertEqual(stem('happy'), 'happi')
        self.assertEqual(stem('sky'), 'sky')
    
    def test_step2_suffixes(self):
        """Step 2: Various suffixes."""
        self.assertEqual(stem('relational'), 'relat')
        self.assertEqual(stem('conditional'), 'condit')
        self.assertEqual(stem('rational'), 'ration')
        self.assertEqual(stem('valenci'), 'valenc')
        self.assertEqual(stem('hesitanci'), 'hesit')
        self.assertEqual(stem('digitizer'), 'digit')
    
    def test_step3_suffixes(self):
        """Step 3: More suffixes."""
        self.assertEqual(stem('triplicate'), 'triplic')
        self.assertEqual(stem('formative'), 'form')
        self.assertEqual(stem('formalize'), 'formal')
        self.assertEqual(stem('electrical'), 'electr')
        self.assertEqual(stem('hopeful'), 'hope')
        self.assertEqual(stem('goodness'), 'good')
    
    def test_common_programming_terms(self):
        """Test common programming-related terms."""
        # These should stem to useful roots
        self.assertEqual(stem('running'), 'run')
        self.assertEqual(stem('runs'), 'run')
        self.assertEqual(stem('files'), 'file')
        self.assertEqual(stem('filing'), 'file')
        self.assertEqual(stem('connections'), 'connect')
        self.assertEqual(stem('connecting'), 'connect')
        self.assertEqual(stem('connected'), 'connect')
        self.assertEqual(stem('processing'), 'process')
        self.assertEqual(stem('processes'), 'process')
    
    def test_edge_cases(self):
        """Test edge cases."""
        self.assertEqual(stem(''), '')
        self.assertEqual(stem('a'), 'a')
        self.assertEqual(stem('I'), 'i')
        self.assertEqual(stem('is'), 'is')
        
    def test_already_stemmed(self):
        """Test that already stemmed words don't change."""
        self.assertEqual(stem('run'), 'run')
        self.assertEqual(stem('file'), 'file')
        self.assertEqual(stem('connect'), 'connect')
    
    def test_idempotent(self):
        """Stemming should be idempotent - stemming twice gives same result."""
        words = ['running', 'files', 'connections', 'happy', 'relational']
        for word in words:
            once = stem(word)
            twice = stem(once)
            self.assertEqual(once, twice, f"Stemming not idempotent for {word}")
    
    def test_stem_tokens(self):
        """Test batch stemming of tokens."""
        tokens = ['running', 'files', 'happy']
        expected = ['run', 'file', 'happi']
        self.assertEqual(stem_tokens(tokens), expected)
    
    def test_preserves_case(self):
        """Stemmer should lowercase output."""
        self.assertEqual(stem('Running'), 'run')
        self.assertEqual(stem('FILES'), 'file')
        self.assertEqual(stem('HaPPy'), 'happi')


class TestTokenizeWithStemming(unittest.TestCase):
    """Test tokenization with stemming enabled."""
    
    def test_tokenize_with_stemming(self):
        """Tokenize with stemming should stem tokens."""
        from doc_search.utils import tokenize
        
        text = "Running files and connecting processes"
        tokens = tokenize(text, stem=True)
        
        # Should contain stemmed versions
        self.assertIn('run', tokens)
        self.assertIn('file', tokens)
        self.assertIn('connect', tokens)
        self.assertIn('process', tokens)
    
    def test_tokenize_without_stemming(self):
        """Tokenize without stemming should keep original words."""
        from doc_search.utils import tokenize
        
        text = "Running files and connecting processes"
        tokens = tokenize(text, stem=False)
        
        # Should contain original forms
        self.assertIn('running', tokens)
        self.assertIn('files', tokens)
        self.assertIn('connecting', tokens)
        self.assertIn('processes', tokens)


if __name__ == '__main__':
    unittest.main()
