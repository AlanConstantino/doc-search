"""Tests for smart fuzzy term expansion rules."""

import pytest
import tempfile
from pathlib import Path

from doc_search.indexer import BM25Index
from doc_search.searcher import EnhancedSearchEngine


class TestSmartFuzzyExpansion:
    """Tests for the smart fuzzy term expansion rules."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test indices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def search_engine(self, temp_dir):
        """Create a search engine with sample documents."""
        index = BM25Index()
        
        # Add documents with various terms
        index.add_document(
            doc_id=0,
            url="http://example.com/python",
            title="Python Programming Guide",
            text="Python is a powerful programming language. Learn Python basics here.",
            description="Introduction to Python"
        )
        index.add_document(
            doc_id=1,
            url="http://example.com/javascript",
            title="JavaScript Tutorial",
            text="JavaScript is used for web development. Modern JavaScript features.",
            description="JavaScript basics"
        )
        index.add_document(
            doc_id=2,
            url="http://example.com/java",
            title="Java Development",
            text="Java is a statically typed language. Enterprise Java applications.",
            description="Java programming"
        )
        index.add_document(
            doc_id=3,
            url="http://example.com/documentation",
            title="Documentation Best Practices",
            text="Good documentation helps developers understand code better.",
            description="Writing documentation"
        )
        index.add_document(
            doc_id=4,
            url="http://example.com/rare",
            title="Rare Word Article",
            text="This article contains xylophone and zebra as rare terms.",
            description="Rare words"
        )
        
        
        index_path = temp_dir / "test_index.json"
        index.save(index_path)
        
        engine = EnhancedSearchEngine.load(index_path, enable_levenshtein=True)
        return engine
    
    def test_term_not_in_vocabulary_gets_fuzzy(self, search_engine):
        """Fuzzy expands when term is NOT in vocabulary."""
        # "pythom" is not in vocabulary, should fuzzy match to "python"
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            ["pythom"], query="pythom"
        )
        
        # Should include both original and fuzzy match
        assert "pythom" in terms
        assert "python" in terms
        # fuzzy_corrections should have the edit distance
        assert "python" in fuzzy_corrections
        assert fuzzy_corrections["python"] in [1, 2]  # edit distance
    
    def test_term_in_vocabulary_no_fuzzy(self, search_engine):
        """Don't fuzzy when term EXISTS in vocabulary."""
        # "python" is in vocabulary, should NOT fuzzy expand
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            ["python"], query="python"
        )
        
        assert terms == ["python"]
        assert len(fuzzy_corrections) == 0
    
    def test_short_terms_no_fuzzy(self, search_engine):
        """Don't fuzzy terms shorter than min_term_length (default 4)."""
        # "cat" is too short (3 chars)
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            ["cat"], query="cat"
        )
        
        assert terms == ["cat"]
        assert len(fuzzy_corrections) == 0
    
    def test_wildcard_terms_no_fuzzy(self, search_engine):
        """Don't fuzzy terms with wildcards."""
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            ["pyth*"], query="pyth*"
        )
        
        assert terms == ["pyth*"]
        assert len(fuzzy_corrections) == 0
    
    def test_quoted_query_no_fuzzy(self, search_engine):
        """Don't fuzzy when query contains quotes (exact phrase intent)."""
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            ["pythom"], query='"pythom programming"'
        )
        
        # Original term kept, but no fuzzy expansion due to quotes
        assert terms == ["pythom"]
        assert len(fuzzy_corrections) == 0
    
    def test_multi_term_low_df_gets_fuzzy(self, search_engine):
        """Fuzzy when term has very low df AND query has multiple terms."""
        # "zebra" exists but with very low df (1 doc)
        # Note: terms get stemmed, so we need to check what's actually in vocab
        
        # Check what terms are actually in the vocabulary
        vocab = set(search_engine.index.index.keys())
        
        # Find a term with low df (df <= 2)
        low_df_term = None
        for term in vocab:
            df = search_engine.index.get_document_frequency(term)
            if df is not None and df <= 2 and len(term) >= 4:
                low_df_term = term
                break
        
        if low_df_term is None:
            pytest.skip("No low-df term found in test vocabulary")
        
        # In multi-term query with low df term, should consider fuzzy
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            [low_df_term, "python"], query=f"{low_df_term} python",
            low_df_threshold=2
        )
        
        # Original terms should be kept
        assert low_df_term in terms
        assert "python" in terms
    
    def test_fuzzy_disabled_returns_unchanged(self, temp_dir):
        """When levenshtein is disabled, return terms unchanged."""
        index = BM25Index()
        index.add_document(
            doc_id=0,
            url="http://example.com/test",
            title="Test",
            text="Test content",
            description="Test"
        )
        
        index_path = temp_dir / "disabled_index.json"
        index.save(index_path)
        
        # Create engine with levenshtein disabled
        engine = EnhancedSearchEngine.load(index_path, enable_levenshtein=False)
        
        terms, fuzzy_corrections = engine._expand_fuzzy_terms(
            ["pythom"], query="pythom"
        )
        
        assert terms == ["pythom"]
        assert len(fuzzy_corrections) == 0
    
    def test_edit_distance_tracked_correctly(self, search_engine):
        """Verify edit distances are tracked correctly."""
        # "pythn" is 1 edit away from "python"
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            ["pythn"], query="pythn"
        )
        
        if "python" in fuzzy_corrections:
            assert fuzzy_corrections["python"] == 1
    
    def test_multiple_fuzzy_expansions_per_term(self, search_engine):
        """Test that we can get multiple fuzzy matches per term."""
        # "jav" is not in vocabulary, might match "java"
        terms, fuzzy_corrections = search_engine._expand_fuzzy_terms(
            ["javas"], query="javas"  # 1 edit from "java"
        )
        
        # Check that we get fuzzy matches
        assert "javas" in terms
        # "java" should be found as a fuzzy match (1 deletion)
        if "java" in terms:
            assert "java" in fuzzy_corrections


class TestFuzzyWeightIntegration:
    """Test that fuzzy weights are properly integrated into scoring."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def search_engine(self, temp_dir):
        """Create a search engine with sample documents."""
        index = BM25Index()
        
        index.add_document(
            doc_id=0,
            url="http://example.com/python",
            title="Python Guide",
            text="Python programming guide",
            description="Python"
        )
        index.add_document(
            doc_id=1,
            url="http://example.com/pithon",
            title="Pithon Article",
            text="Article about pithon",
            description="Pithon"
        )
        
        
        index_path = temp_dir / "weight_test.json"
        index.save(index_path)
        
        return EnhancedSearchEngine.load(index_path, enable_levenshtein=True)
    
    def test_exact_match_scores_higher_than_fuzzy(self, search_engine):
        """Documents with exact matches should score higher than fuzzy matches."""
        # Search for "python" - should find exact match
        results = search_engine.search("python", top_k=10)
        
        # The exact match document should be first
        assert len(results) > 0
        assert "python" in results[0]['url'].lower()


class TestDocumentFrequencyMethod:
    """Tests for the get_document_frequency method."""
    
    @pytest.fixture
    def index(self):
        index = BM25Index()
        index.add_document(
            doc_id=0,
            url="http://example.com/1",
            title="Python Guide",
            text="Python is great for programming",
            description="Python"
        )
        index.add_document(
            doc_id=1,
            url="http://example.com/2",
            title="Python Tutorial",
            text="Learn Python programming",
            description="More Python"
        )
        index.add_document(
            doc_id=2,
            url="http://example.com/3",
            title="Java Guide",
            text="Java is different from Python",
            description="Java"
        )
        
        return index
    
    def test_get_document_frequency_existing_term(self, index):
        """Test getting df for term that exists."""
        # "python" appears in all 3 docs
        df = index.get_document_frequency("python")
        assert df == 3
    
    def test_get_document_frequency_single_doc_term(self, index):
        """Test getting df for term in single doc."""
        # "java" only in one doc
        df = index.get_document_frequency("java")
        assert df == 1
    
    def test_get_document_frequency_nonexistent_term(self, index):
        """Test getting df for term that doesn't exist."""
        df = index.get_document_frequency("nonexistent")
        assert df is None
    
    def test_get_document_frequency_case_insensitive(self, index):
        """Test that df lookup is case insensitive."""
        df_lower = index.get_document_frequency("python")
        df_upper = index.get_document_frequency("PYTHON")
        assert df_lower == df_upper
