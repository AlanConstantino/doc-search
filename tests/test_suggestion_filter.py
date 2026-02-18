"""Tests for suggestion term filtering."""

import pytest
from doc_search.indexer import is_suggestion_worthy, filter_suggestion_terms


class TestIsSuggestionWorthy:
    """Test the is_suggestion_worthy filter."""

    @pytest.mark.parametrize("term", [
        "python", "search", "hello", "api", "doc-search", "my", "ai",
        "http", "html", "json", "python3", "utf8", "algorithm",
        "database", "javascript", "internationalization", "self-hosted",
    ])
    def test_accepts_valid_terms(self, term):
        assert is_suggestion_worthy(term), f"should accept: {term}"

    @pytest.mark.parametrize("term", [
        # Too short
        "a", "b",
        # Underscored variable names
        "p_", "x_", "sum_", "m_", "c_", "t_", "xi_", "vp_", "delta_", "max_",
        # ID-like / hex-like strings
        "s000712340000925x", "abcdef01234567", "tb01752", "ord250301", "s00355",
        # Too many digits relative to letters
        "v35i6", "l2", "v0", "v1", "hs5",
        # Concatenated PDF garbage (too long)
        "scholarlydebateaboutapportionmentproportionalityhasfocusedprimarilyonhowtoquantifytheinevit",
        "propertiesofmultiwinnervot",
        # No vowels (5+ chars)
        "bcdfghjkl", "trstng",
        # Starts with digit
        "3dmodel", "123abc",
    ])
    def test_rejects_junk_terms(self, term):
        assert not is_suggestion_worthy(term), f"should reject: {term}"


class TestFilterSuggestionTerms:
    """Test bulk filtering of doc_freqs."""

    def test_filters_junk_from_doc_freqs(self):
        doc_freqs = {
            "python": 50,
            "search": 30,
            "p_": 10,
            "v35i6": 5,
            "a": 100,
            "algorithm": 20,
        }
        result = filter_suggestion_terms(doc_freqs)
        assert "python" in result
        assert "search" in result
        assert "algorithm" in result
        assert "p_" not in result
        assert "v35i6" not in result
        assert "a" not in result

    def test_preserves_frequencies(self):
        doc_freqs = {"python": 50, "search": 30}
        result = filter_suggestion_terms(doc_freqs)
        assert result["python"] == 50
        assert result["search"] == 30

    def test_empty_input(self):
        assert filter_suggestion_terms({}) == {}
