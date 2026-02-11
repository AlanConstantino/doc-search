"""Tests for Levenshtein automaton and fuzzy matching."""

import pytest
from doc_search.levenshtein import (
    LevenshteinAutomaton,
    LevenshteinMatcher,
    levenshtein_distance,
    damerau_levenshtein_distance,
    State
)


class TestLevenshteinDistance:
    """Tests for classic Levenshtein distance function."""
    
    def test_identical_strings(self):
        assert levenshtein_distance("test", "test") == 0
    
    def test_empty_strings(self):
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("test", "") == 4
        assert levenshtein_distance("", "test") == 4
    
    def test_single_insertion(self):
        assert levenshtein_distance("test", "tests") == 1
        assert levenshtein_distance("test", "ttest") == 1
    
    def test_single_deletion(self):
        assert levenshtein_distance("tests", "test") == 1
        assert levenshtein_distance("ttest", "test") == 1
    
    def test_single_substitution(self):
        assert levenshtein_distance("test", "best") == 1
        assert levenshtein_distance("test", "text") == 1
    
    def test_multiple_edits(self):
        assert levenshtein_distance("kitten", "sitting") == 3
        assert levenshtein_distance("saturday", "sunday") == 3
    
    def test_case_insensitive(self):
        assert levenshtein_distance("Test", "test") == 0
        assert levenshtein_distance("TEST", "test") == 0


class TestDamerauLevenshteinDistance:
    """Tests for Damerau-Levenshtein distance (with transpositions)."""
    
    def test_identical_strings(self):
        assert damerau_levenshtein_distance("test", "test") == 0
    
    def test_transposition(self):
        # tset -> test is 1 transposition
        assert damerau_levenshtein_distance("tset", "test") == 1
        assert damerau_levenshtein_distance("ab", "ba") == 1
    
    def test_transposition_vs_substitution(self):
        # Transposition should be cheaper than 2 substitutions
        assert damerau_levenshtein_distance("ab", "ba") == 1
        assert levenshtein_distance("ab", "ba") == 2
    
    def test_multiple_transpositions(self):
        assert damerau_levenshtein_distance("abcd", "badc") == 2


class TestLevenshteinAutomaton:
    """Tests for Levenshtein automaton."""
    
    def test_exact_match(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        assert auto.accepts("test") is True
    
    def test_case_insensitive(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        assert auto.accepts("TEST") is True
        assert auto.accepts("Test") is True
    
    def test_single_insertion(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        assert auto.accepts("tests") is True
        assert auto.accepts("ttest") is True
        assert auto.accepts("testt") is True
    
    def test_single_deletion(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        assert auto.accepts("tes") is True
        assert auto.accepts("est") is True
        assert auto.accepts("tst") is True
    
    def test_single_substitution(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        assert auto.accepts("best") is True
        assert auto.accepts("text") is True
        assert auto.accepts("tast") is True
    
    def test_exceeds_distance(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        assert auto.accepts("hello") is False
        assert auto.accepts("testing") is False  # 3 insertions
        assert auto.accepts("te") is False  # 2 deletions
    
    def test_distance_2(self):
        auto = LevenshteinAutomaton("test", max_distance=2)
        assert auto.accepts("testing") is False  # 3 insertions
        assert auto.accepts("tests!") is True  # 2 insertions
        assert auto.accepts("te") is True  # 2 deletions
        assert auto.accepts("bast") is True  # 2 substitutions
    
    def test_get_distance_exact(self):
        auto = LevenshteinAutomaton("test", max_distance=2)
        assert auto.get_distance("test") == 0
    
    def test_get_distance_one_edit(self):
        auto = LevenshteinAutomaton("test", max_distance=2)
        assert auto.get_distance("tests") == 1
        assert auto.get_distance("tes") == 1
        assert auto.get_distance("best") == 1
    
    def test_get_distance_exceeds(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        assert auto.get_distance("hello") is None
    
    def test_empty_pattern(self):
        auto = LevenshteinAutomaton("", max_distance=2)
        assert auto.accepts("") is True
        assert auto.accepts("a") is True
        assert auto.accepts("ab") is True
        assert auto.accepts("abc") is False
    
    def test_empty_word(self):
        auto = LevenshteinAutomaton("ab", max_distance=2)
        assert auto.accepts("") is True
        
        auto = LevenshteinAutomaton("abc", max_distance=2)
        assert auto.accepts("") is False
    
    def test_find_matches(self):
        auto = LevenshteinAutomaton("test", max_distance=1)
        vocab = ["test", "tests", "best", "rest", "hello", "testing"]
        matches = auto.find_matches(vocab)
        
        # Should find test (0), tests (1), best (1), rest (1)
        terms = [m[0] for m in matches]
        assert "test" in terms
        assert "tests" in terms
        assert "best" in terms
        assert "rest" in terms
        assert "hello" not in terms
        assert "testing" not in terms


class TestLevenshteinMatcher:
    """Tests for vocabulary-based fuzzy matcher."""
    
    @pytest.fixture
    def vocab(self):
        return [
            "python", "pythonic", "pythons",
            "java", "javascript",
            "function", "functions",
            "test", "testing", "tests",
            "hello", "world"
        ]
    
    @pytest.fixture
    def matcher(self, vocab):
        return LevenshteinMatcher(vocab)
    
    def test_exact_match(self, matcher):
        matches = matcher.find_similar("python", max_distance=1)
        assert len(matches) > 0
        assert matches[0] == ("python", 0)
    
    def test_typo_correction(self, matcher):
        # pythom -> python (1 substitution)
        matches = matcher.find_similar("pythom", max_distance=1)
        assert ("python", 1) in matches
    
    def test_transposition_like(self, matcher):
        # tset -> test (needs 2 edits in standard Levenshtein)
        matches = matcher.find_similar("tset", max_distance=2)
        assert any(m[0] == "test" for m in matches)
    
    def test_prefix_match(self, matcher):
        # pyth -> python (2 insertions)
        matches = matcher.find_similar("pyth", max_distance=2)
        assert ("python", 2) in matches
    
    def test_no_matches(self, matcher):
        matches = matcher.find_similar("xyz", max_distance=1)
        assert len(matches) == 0
    
    def test_max_results(self, matcher):
        matches = matcher.find_similar("test", max_distance=2, max_results=2)
        assert len(matches) <= 2
    
    def test_find_best_match(self, matcher):
        best = matcher.find_best_match("pythom")
        assert best == "python"
    
    def test_find_best_match_no_match(self, matcher):
        best = matcher.find_best_match("xyz", max_distance=1)
        assert best is None
    
    def test_case_insensitive(self, matcher):
        matches = matcher.find_similar("PYTHON", max_distance=0)
        assert ("python", 0) in matches
    
    def test_frequency_ranking(self, matcher):
        matcher.set_frequencies({"tests": 100, "test": 50})
        matches = matcher.find_similar("test", max_distance=1)
        
        # Both should be in results
        test_idx = next(i for i, m in enumerate(matches) if m[0] == "test")
        tests_idx = next(i for i, m in enumerate(matches) if m[0] == "tests")
        
        # At same distance, higher frequency should come first
        # test has distance 0, tests has distance 1, so test should be first
        assert test_idx < tests_idx


class TestState:
    """Tests for automaton State class."""
    
    def test_state_hashable(self):
        s1 = State(0, 0)
        s2 = State(0, 0)
        assert hash(s1) == hash(s2)
        assert s1 == s2
    
    def test_state_in_set(self):
        states = {State(0, 0), State(1, 0), State(0, 1)}
        assert State(0, 0) in states
        assert State(2, 0) not in states
    
    def test_state_repr(self):
        s = State(5, 2)
        assert repr(s) == "S(5,2)"


class TestEdgeCases:
    """Edge case tests."""
    
    def test_single_char_pattern(self):
        auto = LevenshteinAutomaton("a", max_distance=1)
        assert auto.accepts("a") is True
        assert auto.accepts("b") is True  # substitution
        assert auto.accepts("") is True  # deletion
        assert auto.accepts("ab") is True  # insertion
        assert auto.accepts("abc") is False  # 2 insertions
    
    def test_single_char_word(self):
        auto = LevenshteinAutomaton("abc", max_distance=1)
        assert auto.accepts("a") is False  # need 2 deletions
        assert auto.accepts("ab") is True  # 1 deletion
    
    def test_unicode(self):
        auto = LevenshteinAutomaton("café", max_distance=1)
        assert auto.accepts("café") is True
        assert auto.accepts("cafe") is True  # 1 substitution
    
    def test_long_string(self):
        pattern = "documentation"
        auto = LevenshteinAutomaton(pattern, max_distance=2)
        assert auto.accepts("documentation") is True
        assert auto.accepts("documentaton") is True  # 1 deletion
        assert auto.accepts("documnetation") is True  # transposition-like
    
    def test_max_distance_zero(self):
        auto = LevenshteinAutomaton("test", max_distance=0)
        assert auto.accepts("test") is True
        assert auto.accepts("tests") is False
        assert auto.accepts("tes") is False
        assert auto.accepts("best") is False


class TestPerformance:
    """Performance-related tests."""
    
    def test_large_vocabulary(self):
        """Test matcher with larger vocabulary."""
        # Generate vocabulary
        vocab = [f"word{i}" for i in range(1000)]
        vocab.extend(["test", "testing", "tests", "tester"])
        
        matcher = LevenshteinMatcher(vocab)
        matches = matcher.find_similar("test", max_distance=1)
        
        assert ("test", 0) in matches
        assert ("tests", 1) in matches
    
    def test_early_termination(self):
        """Verify automaton enables early termination."""
        auto = LevenshteinAutomaton("test", max_distance=1)
        
        # Long string that diverges early should terminate quickly
        # (though we can't easily verify timing, we check correctness)
        long_word = "x" * 100
        assert auto.accepts(long_word) is False
    
    def test_cache_effectiveness(self):
        """Test that transition cache is used."""
        auto = LevenshteinAutomaton("test", max_distance=1)
        
        # Run same word twice
        auto.accepts("testing")
        cache_size_1 = len(auto._transition_cache)
        
        auto.accepts("testing")
        cache_size_2 = len(auto._transition_cache)
        
        # Cache should have entries and not grow on repeat
        assert cache_size_1 > 0
        assert cache_size_2 == cache_size_1
