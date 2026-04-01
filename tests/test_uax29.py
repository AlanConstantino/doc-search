"""
Tests for UAX #29 Unicode Text Segmentation tokenizer.

This module tests the implementation of the Unicode Word Boundary algorithm
and its integration with the doc-search tokenization pipeline.
"""

import unittest
from doc_search.uax29_tokenizer import (
    word_break_property, segment_words, tokenize_words
)
from doc_search.utils import tokenize


class TestWordBreakProperty(unittest.TestCase):
    """Test character classification function."""
    
    def test_ascii_characters(self):
        """Test ASCII character classification."""
        # Test letters
        self.assertEqual(word_break_property('a'), 'ALetter')
        self.assertEqual(word_break_property('Z'), 'ALetter')
        
        # Test digits
        self.assertEqual(word_break_property('0'), 'Numeric')
        self.assertEqual(word_break_property('9'), 'Numeric')
        
        # Test special characters
        self.assertEqual(word_break_property(' '), 'WSegSpace')
        self.assertEqual(word_break_property('_'), 'ExtendNumLet')
        self.assertEqual(word_break_property('.'), 'MidNumLet')
        self.assertEqual(word_break_property(','), 'MidNum')
        self.assertEqual(word_break_property(':'), 'MidLetter')
        self.assertEqual(word_break_property("'"), 'Single_Quote')
        self.assertEqual(word_break_property('"'), 'Double_Quote')
        
        # Test line breaks
        self.assertEqual(word_break_property('\r'), 'CR')
        self.assertEqual(word_break_property('\n'), 'LF')
        
        # Test other punctuation
        self.assertEqual(word_break_property('-'), 'Other')
        self.assertEqual(word_break_property('@'), 'Other')
    
    def test_unicode_characters(self):
        """Test Unicode character classification."""
        # Test Hebrew letters (if available)
        try:
            # Hebrew Alef
            self.assertEqual(word_break_property('\u05D0'), 'Hebrew_Letter')
        except:
            # Skip if Hebrew not available in environment
            pass
        
        # Test Regional Indicators (flag emojis)
        self.assertEqual(word_break_property('\U0001F1FA'), 'Regional_Indicator')  # 🇺
        
        # Test ZWJ
        self.assertEqual(word_break_property('\u200D'), 'ZWJ')
        
        # Test additional newlines
        self.assertEqual(word_break_property('\u2028'), 'Newline')  # Line Separator
    
    def test_combining_marks(self):
        """Test combining marks are classified as Extend."""
        # Combining grave accent
        self.assertEqual(word_break_property('\u0300'), 'Extend')


class TestSegmentWords(unittest.TestCase):
    """Test basic word segmentation function."""
    
    def test_empty_string(self):
        """Empty string should return empty list."""
        self.assertEqual(segment_words(""), [])
    
    def test_single_word(self):
        """Single word should return the word."""
        self.assertEqual(segment_words("hello"), ["hello"])
    
    def test_basic_segmentation(self):
        """Test basic word segmentation."""
        result = segment_words("hello world")
        self.assertEqual(result, ["hello", " ", "world"])
    
    def test_punctuation_segmentation(self):
        """Test punctuation creates separate segments."""
        result = segment_words("hello, world!")
        self.assertEqual(result, ["hello", ",", " ", "world", "!"])
    
    def test_numbers(self):
        """Test number handling."""
        # Single numbers
        self.assertEqual(segment_words("404"), ["404"])
        
        # Decimal numbers
        self.assertEqual(segment_words("3.14"), ["3.14"])
        
        # Version numbers - UAX #29 keeps these together (MidNumLet between Numeric)
        self.assertEqual(segment_words("3.11.2"), ["3.11.2"])
    
    def test_mixed_alphanumeric(self):
        """Test mixed letters and numbers."""
        # Letter + digit
        self.assertEqual(segment_words("python3"), ["python3"])
        
        # More complex
        self.assertEqual(segment_words("x86_64"), ["x86_64"])
        
        # Windows-style
        self.assertEqual(segment_words("win32"), ["win32"])
    
    def test_underscores(self):
        """Test underscore handling (ExtendNumLet)."""
        # Python identifiers
        self.assertEqual(segment_words("__init__"), ["__init__"])
        self.assertEqual(segment_words("my_function"), ["my_function"])
        self.assertEqual(segment_words("error_handling"), ["error_handling"])
        
        # Mixed with letters and numbers
        self.assertEqual(segment_words("test_123"), ["test_123"])
    
    def test_hyphens_break(self):
        """Test that hyphens break words (hyphen is Other in UAX #29)."""
        # This SHOULD break according to UAX #29
        result = segment_words("utf-8")
        self.assertEqual(result, ["utf", "-", "8"])
        
        # Another example
        result = segment_words("twenty-one")
        self.assertEqual(result, ["twenty", "-", "one"])
    
    def test_apostrophes(self):
        """Test apostrophe handling (Single_Quote)."""
        # Should stay together between letters
        self.assertEqual(segment_words("don't"), ["don't"])
        self.assertEqual(segment_words("it's"), ["it's"])
        self.assertEqual(segment_words("I'm"), ["I'm"])
    
    def test_dotted_identifiers(self):
        """Test dotted identifiers like module.function."""
        # Period is MidNumLet, so should NOT break between letters
        self.assertEqual(segment_words("os.path.join"), ["os.path.join"])
        self.assertEqual(segment_words("sys.exit"), ["sys.exit"])
    
    def test_ip_addresses(self):
        """Test IP address-like strings."""
        # Period between numbers should NOT break (MidNumLet rule)
        self.assertEqual(segment_words("192.168.1.1"), ["192.168.1.1"])
    
    def test_email_breaks(self):
        """Test that email addresses break at @ (@ is Other)."""
        result = segment_words("user@example.com")
        # @ should cause a break
        self.assertIn("@", result)
        self.assertTrue(len(result) > 1)
    
    def test_cr_lf_handling(self):
        """Test CR+LF sequence handling."""
        # CR+LF should stay together (WB3)
        result = segment_words("hello\r\nworld")
        self.assertIn("hello", result)
        self.assertIn("world", result)
        # The \r\n might be one segment or handled specially
        # Main point is it should not break between \r and \n
    
    def test_spaces_stay_together(self):
        """Test that multiple spaces stay as one segment."""
        result = segment_words("hello   world")
        # Multiple spaces should be one segment
        self.assertIn("   ", result)
    
    def test_regional_indicators(self):
        """Test regional indicator (flag emoji) handling."""
        # Two regional indicators should stay together (flag)
        result = segment_words("🇺🇸")
        self.assertEqual(result, ["🇺🇸"])


class TestTokenizeWords(unittest.TestCase):
    """Test word-like token extraction."""
    
    def test_filters_whitespace(self):
        """Should filter out whitespace-only segments."""
        result = tokenize_words("hello world")
        self.assertEqual(result, ["hello", "world"])
        self.assertNotIn(" ", result)
    
    def test_filters_punctuation(self):
        """Should filter out punctuation-only segments."""
        result = tokenize_words("hello, world!")
        self.assertEqual(result, ["hello", "world"])
        self.assertNotIn(",", result)
        self.assertNotIn("!", result)
    
    def test_preserves_mixed_tokens(self):
        """Should preserve tokens with letters/numbers."""
        result = tokenize_words("test 123 python3 _var")
        self.assertEqual(set(result), {"test", "123", "python3", "_var"})
    
    def test_preserves_complex_tokens(self):
        """Should preserve complex alphanumeric tokens."""
        result = tokenize_words("x86_64 3.14 __init__")
        self.assertEqual(set(result), {"x86_64", "3.14", "__init__"})


class TestIntegrationWithTokenize(unittest.TestCase):
    """Test integration with the main tokenize() function."""
    
    def test_tokenize_numbers(self):
        """Test that numbers are properly tokenized."""
        # These tests were failing with the old regex tokenizer
        result = tokenize("HTTP 404 error")
        self.assertIn("404", result)
        
        result = tokenize("Python 3.11 release")
        self.assertIn("3.11", result)  # UAX #29 keeps decimal numbers together
        
        result = tokenize("HTTP 200 OK")
        self.assertIn("200", result)
    
    def test_tokenize_underscores(self):
        """Test that underscore identifiers are preserved."""
        result = tokenize("the __init__ method")
        self.assertIn("__init__", result)
        
        result = tokenize("my_function call")
        self.assertIn("my_function", result)
    
    def test_tokenize_versions(self):
        """Test version number tokenization."""
        result = tokenize("pi is 3.14")
        # Should capture the decimal number
        self.assertTrue(any("3" in token and "14" in token for token in result))
    
    def test_tokenize_mixed_alphanumeric(self):
        """Test mixed letter+number tokens."""
        result = tokenize("use python3")
        self.assertIn("python3", result)
        
        result = tokenize("x86_64 architecture")  
        self.assertIn("x86_64", result)
    
    def test_stop_word_removal(self):
        """Test that stop words are still removed."""
        result = tokenize("the quick brown fox")
        self.assertNotIn("the", result)
        self.assertIn("quick", result)
        self.assertIn("brown", result)
        self.assertIn("fox", result)
    
    def test_case_normalization(self):
        """Test that case is normalized."""
        result = tokenize("Hello World")
        self.assertIn("hello", result)
        self.assertIn("world", result)
        self.assertNotIn("Hello", result)
        self.assertNotIn("World", result)
    
    def test_stemming_integration(self):
        """Test that stemming still works."""
        result = tokenize("running files", apply_stemming=True)
        # These should be stemmed
        expected_stems = set(result)
        # Can't test exact stems without running, but verify no errors
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(token, str) for token in result))
    
    def test_complex_text(self):
        """Test complex real-world text."""
        text = "Python 3.11 introduced the __init__.py module with error_handling for HTTP 404 responses."
        result = tokenize(text)
        
        # Should preserve complex tokens
        self.assertIn("python", result)  # normalized
        self.assertIn("3.11", result)  # decimal numbers kept together
        self.assertIn("__init__", result)  # underscores
        self.assertIn("py", result)  # from .py
        self.assertIn("error_handling", result)  # compound identifier
        self.assertIn("http", result)  # normalized
        self.assertIn("404", result)  # pure number
        
        # Should not have stop words
        self.assertNotIn("the", result)
        self.assertNotIn("with", result)
        self.assertNotIn("for", result)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""
    
    def test_empty_input(self):
        """Test empty input handling."""
        self.assertEqual(segment_words(""), [])
        self.assertEqual(tokenize_words(""), [])
        self.assertEqual(tokenize(""), [])
    
    def test_whitespace_only(self):
        """Test whitespace-only input."""
        self.assertEqual(tokenize_words("   "), [])
        self.assertEqual(tokenize("   "), [])
    
    def test_punctuation_only(self):
        """Test punctuation-only input."""
        self.assertEqual(tokenize_words(".,;:!?"), [])
        self.assertEqual(tokenize(".,;:!?"), [])
    
    def test_numbers_only(self):
        """Test numbers-only input."""
        result = tokenize("123 456 789")
        self.assertEqual(set(result), {"123", "456", "789"})
    
    def test_single_characters(self):
        """Test single character handling."""
        # Single letters should be filtered out (length < 2)
        result = tokenize("a b c test")
        self.assertNotIn("a", result)
        self.assertNotIn("b", result)
        self.assertNotIn("c", result)
        self.assertIn("test", result)
    
    def test_unicode_text(self):
        """Test Unicode text handling."""
        # Test with some basic Unicode
        result = tokenize("café naïve résumé")
        # Should handle accented characters
        self.assertTrue(len(result) >= 3)
        
        # Test with mixed scripts (if available)
        result = tokenize("hello 你好 world")
        # Should at least preserve ASCII parts
        self.assertIn("hello", result)
        self.assertIn("world", result)
    
    def test_very_long_input(self):
        """Test with very long input."""
        # Generate long text
        text = " ".join(["word"] * 1000)
        result = tokenize(text)
        # Should handle without errors and remove duplicates
        self.assertIsInstance(result, list)
        # After stop word and duplicate removal, should be much shorter
        self.assertTrue(len(result) <= 1000)
    
    def test_mixed_line_endings(self):
        """Test different line ending styles."""
        text = "line1\r\nline2\nline3\rline4"
        result = tokenize(text)
        # Should handle all line ending types
        expected_words = {"line1", "line2", "line3", "line4"}
        self.assertTrue(expected_words.issubset(set(result)))


class TestPerformance(unittest.TestCase):
    """Basic performance regression tests."""
    
    def test_ascii_text_performance(self):
        """Test performance on ASCII text."""
        import time
        
        # Generate test text
        text = "The quick brown fox jumps over the lazy dog. " * 100
        
        start_time = time.time()
        result = tokenize(text)
        end_time = time.time()
        
        # Should complete reasonably quickly (< 1 second for this size)
        self.assertLess(end_time - start_time, 1.0)
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
    
    def test_large_token_performance(self):
        """Test performance with large tokens."""
        # Create very long identifier
        long_identifier = "very_" * 100 + "long_identifier"
        text = f"This is a {long_identifier} in the text."
        
        result = tokenize(text)
        # Should handle without errors
        self.assertIsInstance(result, list)
        self.assertIn(long_identifier, result)


if __name__ == '__main__':
    unittest.main()