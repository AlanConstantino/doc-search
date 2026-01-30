"""
Tests for search functionality including phrase search and highlighting.
"""

import unittest
from doc_search.searcher import (
    parse_query, 
    check_phrase_match, 
    find_phrase_positions,
    highlight_terms, 
    find_best_snippet
)


class TestParseQuery(unittest.TestCase):
    """Tests for query parsing."""
    
    def test_simple_terms(self):
        """Simple query with no phrases."""
        terms, phrases = parse_query('python tutorial')
        self.assertIn('python', terms)
        self.assertIn('tutorial', terms)
        self.assertEqual(phrases, [])
    
    def test_single_phrase(self):
        """Query with a single phrase."""
        terms, phrases = parse_query('"list comprehension"')
        self.assertEqual(terms, [])
        self.assertEqual(phrases, [['list', 'comprehension']])
    
    def test_mixed_terms_and_phrases(self):
        """Query with both terms and phrases."""
        terms, phrases = parse_query('python "list comprehension" tutorial')
        self.assertIn('python', terms)
        self.assertIn('tutorial', terms)
        self.assertEqual(phrases, [['list', 'comprehension']])
    
    def test_multiple_phrases(self):
        """Query with multiple phrases."""
        terms, phrases = parse_query('"list comprehension" "context manager"')
        self.assertEqual(len(phrases), 2)
        self.assertIn(['list', 'comprehension'], phrases)
        self.assertIn(['context', 'manager'], phrases)
    
    def test_empty_query(self):
        """Empty query returns empty results."""
        terms, phrases = parse_query('')
        self.assertEqual(terms, [])
        self.assertEqual(phrases, [])


class TestPhraseMatch(unittest.TestCase):
    """Tests for phrase matching."""
    
    def test_phrase_found(self):
        """Phrase appears in text."""
        text = 'Python supports list comprehension for concise code'
        self.assertTrue(check_phrase_match(text, ['list', 'comprehension']))
    
    def test_phrase_not_found_wrong_order(self):
        """Phrase words in wrong order should not match."""
        text = 'A comprehension of this list'
        self.assertFalse(check_phrase_match(text, ['list', 'comprehension']))
    
    def test_phrase_not_found_separated(self):
        """Phrase words separated by other words should not match."""
        text = 'list of items with comprehension'
        self.assertFalse(check_phrase_match(text, ['list', 'comprehension']))
    
    def test_empty_phrase(self):
        """Empty phrase matches anything."""
        self.assertTrue(check_phrase_match('any text', []))
    
    def test_phrase_case_insensitive(self):
        """Phrase matching should be case insensitive."""
        text = 'Python List Comprehension'
        self.assertTrue(check_phrase_match(text, ['list', 'comprehension']))


class TestHighlightTerms(unittest.TestCase):
    """Tests for term highlighting."""
    
    def test_single_term(self):
        """Highlight single term."""
        text = 'Python is great'
        result = highlight_terms(text, {'python'})
        self.assertIn('**Python**', result)
    
    def test_multiple_terms(self):
        """Highlight multiple terms."""
        text = 'Python tutorial for beginners'
        result = highlight_terms(text, {'python', 'tutorial'})
        self.assertIn('**Python**', result)
        self.assertIn('**tutorial**', result)
    
    def test_case_preserved(self):
        """Original case should be preserved in highlighted text."""
        text = 'PYTHON Python python'
        result = highlight_terms(text, {'python'})
        self.assertIn('**PYTHON**', result)
        self.assertIn('**Python**', result)
        self.assertIn('**python**', result)
    
    def test_no_terms(self):
        """No terms means no changes."""
        text = 'Python is great'
        result = highlight_terms(text, set())
        self.assertEqual(text, result)
    
    def test_empty_text(self):
        """Empty text returns empty string."""
        result = highlight_terms('', {'python'})
        self.assertEqual(result, '')


class TestFindBestSnippet(unittest.TestCase):
    """Tests for finding the best snippet."""
    
    def test_short_text_returned_whole(self):
        """Text shorter than snippet_length returned whole."""
        text = 'Short text about Python.'
        result = find_best_snippet(text, {'python'}, [], 200)
        self.assertEqual(text, result)
    
    def test_finds_term_dense_section(self):
        """Snippet should include section with query terms."""
        text = 'Intro paragraph about nothing. Second paragraph about Python list comprehension which is great. Final paragraph about other stuff.'
        result = find_best_snippet(text, {'python', 'list', 'comprehension'}, [], 100)
        # Should contain the terms
        self.assertIn('python', result.lower())
        self.assertIn('list', result.lower())
    
    def test_phrase_bonus(self):
        """Sections with phrase matches should be preferred."""
        text = 'List and comprehension here separately. Another section. Here is list comprehension together. Final section.'
        result = find_best_snippet(text, {'list', 'comprehension'}, [['list', 'comprehension']], 80)
        # Should prefer the section with phrase
        self.assertIn('list comprehension', result.lower())


class TestIntegration(unittest.TestCase):
    """Integration tests."""
    
    def test_full_workflow(self):
        """Test parse -> find snippet -> highlight."""
        query = 'python "list comprehension"'
        text = 'Some intro text. Python list comprehension makes code concise and readable. More text follows here.'
        
        # Parse query
        terms, phrases = parse_query(query)
        
        # Find best snippet
        all_terms = set(terms)
        for p in phrases:
            all_terms.update(p)
        
        snippet = find_best_snippet(text, all_terms, phrases, 100)
        
        # Highlight
        result = highlight_terms(snippet, all_terms)
        
        # Verify
        self.assertIn('**Python**', result)
        self.assertIn('**list**', result)
        self.assertIn('**comprehension**', result)


if __name__ == '__main__':
    unittest.main()
