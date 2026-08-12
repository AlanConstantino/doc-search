"""
Tests for the two-stage retrieval reranking module.
"""

import unittest
from typing import Dict, Any, List, Optional

from doc_search.reranker import (
    Reranker, 
    RerankConfig, 
    RerankMetrics,
    check_phrase_proximity
)


class TestRerankConfig(unittest.TestCase):
    """Tests for RerankConfig dataclass."""
    
    def test_default_config(self):
        """Should have sensible defaults."""
        config = RerankConfig()
        
        self.assertEqual(config.recall_multiplier, 4)
        self.assertEqual(config.max_candidates, 200)
        self.assertEqual(config.candidate_limit, 80)
        self.assertAlmostEqual(config.weight_bm25, 0.55)
        self.assertAlmostEqual(config.weight_field, 0.25)
        self.assertAlmostEqual(config.weight_coverage, 0.10)
        self.assertAlmostEqual(config.weight_phrase, 0.10)
        # Field weights
        self.assertAlmostEqual(config.field_weight_title, 5.0)
        self.assertAlmostEqual(config.field_weight_headings, 2.5)
        self.assertAlmostEqual(config.field_weight_body, 1.0)
    
    def test_custom_config(self):
        """Should accept custom values."""
        config = RerankConfig(
            recall_multiplier=5,
            weight_bm25=0.5,
            coverage_beta=0.5,
            field_weight_title=10.0
        )
        
        self.assertEqual(config.recall_multiplier, 5)
        self.assertAlmostEqual(config.weight_bm25, 0.5)
        self.assertAlmostEqual(config.coverage_beta, 0.5)
        self.assertAlmostEqual(config.field_weight_title, 10.0)


class TestRerankerRecall(unittest.TestCase):
    """Tests for recall stage computations."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def test_compute_recall_k_basic(self):
        """Should multiply top_k by recall_multiplier."""
        # Default multiplier is 4 (tighter serve profile)
        self.assertEqual(self.reranker.compute_recall_k(10), 40)
        self.assertEqual(self.reranker.compute_recall_k(20), 80)

    def test_compute_recall_k_capped(self):
        """Should cap at max_candidates."""
        # Default max is 200
        self.assertEqual(self.reranker.compute_recall_k(100), 200)  # 100*4=400, capped to 200
    
    def test_compute_recall_k_custom_config(self):
        """Should respect custom config."""
        config = RerankConfig(recall_multiplier=5, max_candidates=200)
        reranker = Reranker(config)
        
        self.assertEqual(reranker.compute_recall_k(10), 50)
        self.assertEqual(reranker.compute_recall_k(50), 200)  # Capped


class TestRerankScoring(unittest.TestCase):
    """Tests for individual scoring components."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def test_term_matches_full(self):
        """Should return 1.0 when all terms match."""
        score = self.reranker._compute_term_matches(
            "Python Tutorial Guide",
            ["python", "tutorial"]
        )
        self.assertAlmostEqual(score, 1.0)
    
    def test_term_matches_partial(self):
        """Should return fraction for partial match."""
        score = self.reranker._compute_term_matches(
            "Python Guide",
            ["python", "tutorial"]
        )
        self.assertAlmostEqual(score, 0.5)
    
    def test_term_matches_none(self):
        """Should return 0.0 when no terms match."""
        score = self.reranker._compute_term_matches(
            "JavaScript Guide",
            ["python", "tutorial"]
        )
        self.assertAlmostEqual(score, 0.0)
    
    def test_term_matches_case_insensitive(self):
        """Should match case-insensitively."""
        score = self.reranker._compute_term_matches(
            "PYTHON TUTORIAL",
            ["python", "tutorial"]
        )
        self.assertAlmostEqual(score, 1.0)
    
    def test_coverage_score_full(self):
        """Should give boost for full coverage."""
        score = self.reranker._compute_coverage_score(
            "python list comprehension tutorial",
            ["python", "list", "comprehension"],
            beta=0.4
        )
        # Full coverage: 1 + beta + full_coverage_bonus
        bonus = self.reranker.config.full_coverage_bonus
        self.assertAlmostEqual(score, 1.0 + 0.4 + bonus)
    
    def test_coverage_score_partial(self):
        """Should give proportional boost for partial coverage."""
        score = self.reranker._compute_coverage_score(
            "python basics",
            ["python", "list", "comprehension"],
            beta=0.4
        )
        # 1/3 coverage: 1 + 0.4 * (1/3) ≈ 1.133
        self.assertAlmostEqual(score, 1 + 0.4 * (1/3), places=3)
    
    def test_coverage_score_empty_terms(self):
        """Should return 1.0 for empty terms (no boost)."""
        score = self.reranker._compute_coverage_score("some text", [], beta=0.4)
        self.assertAlmostEqual(score, 1.0)
    
    def test_coverage_score_weighted(self):
        """Should use term weights when provided."""
        # Without weights
        unweighted = self.reranker._compute_coverage_score(
            "python basics",
            ["python", "list", "comprehension"],
            beta=0.4
        )
        
        # With weights favoring "python"
        weighted = self.reranker._compute_coverage_score(
            "python basics",
            ["python", "list", "comprehension"],
            beta=0.4,
            term_weights={"python": 3.0, "list": 1.0, "comprehension": 1.0}
        )
        
        # Weighted coverage should be higher (python has 3x weight)
        self.assertGreater(weighted, unweighted)
    
    def test_coverage_score_long_query_capped(self):
        """Should cap terms considered for very long queries."""
        # Create a long query with 15 terms
        long_terms = [f"term{i}" for i in range(15)]
        text = " ".join(long_terms[:3])  # Only first 3 match
        
        # With default max_coverage_terms=8, only 8 terms considered
        score = self.reranker._compute_coverage_score(
            text, long_terms, beta=0.4
        )
        
        # 3 out of 8 matched (capped) = 37.5% coverage
        expected = 1 + 0.4 * (3 / 8)
        self.assertAlmostEqual(score, expected, places=2)
    
    def test_weighted_coverage_helper(self):
        """Should compute weighted coverage ratio."""
        coverage = self.reranker._compute_weighted_coverage(
            "python list basics",
            ["python", "list", "comprehension"],
            {"python": 2.0, "list": 1.0, "comprehension": 1.0}
        )
        # python (2.0) + list (1.0) matched, total weight = 4.0
        # coverage = 3.0 / 4.0 = 0.75
        self.assertAlmostEqual(coverage, 0.75)
    
    def test_phrase_score_exact_match_in_title(self):
        """Should give high score for exact phrase in title."""
        score = self.reranker._compute_phrase_score(
            "python tutorial for beginners",
            [["python", "tutorial"]],
            in_title=True
        )
        self.assertGreater(score, 0.5)
    
    def test_phrase_score_exact_match_in_body(self):
        """Should give lower score for exact phrase in body."""
        title_score = self.reranker._compute_phrase_score(
            "python tutorial",
            [["python", "tutorial"]],
            in_title=True
        )
        body_score = self.reranker._compute_phrase_score(
            "python tutorial",
            [["python", "tutorial"]],
            in_title=False
        )
        self.assertGreater(title_score, body_score)
    
    def test_proximity_scoring(self):
        """Should score based on word proximity."""
        # Adjacent words
        close_score = self.reranker._score_proximity(
            "python tutorial guide",
            ["python", "tutorial"]
        )
        
        # Words far apart
        far_score = self.reranker._score_proximity(
            "python is a great language for learning and this tutorial helps",
            ["python", "tutorial"]
        )
        
        self.assertGreater(close_score, far_score)
    
    def test_proximity_all_terms_required(self):
        """Should return 0 if not all terms are present."""
        score = self.reranker._score_proximity(
            "python is great",
            ["python", "tutorial"]
        )
        self.assertAlmostEqual(score, 0.0)


class TestFieldAwareScoring(unittest.TestCase):
    """Tests for field-aware ranking (title > headings > body)."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def test_field_score_title_only(self):
        """Title matches should score high even without body matches."""
        score = self.reranker._compute_field_score(
            title="Python Tutorial",
            headings_text="",
            body_text="",
            terms=["python", "tutorial"]
        )
        self.assertGreater(score, 0.5)  # Title has high weight
    
    def test_field_score_body_only(self):
        """Body-only matches should score lower than title matches."""
        title_score = self.reranker._compute_field_score(
            title="Python Tutorial",
            headings_text="",
            body_text="",
            terms=["python", "tutorial"]
        )
        body_score = self.reranker._compute_field_score(
            title="Guide",
            headings_text="",
            body_text="python tutorial content",
            terms=["python", "tutorial"]
        )
        self.assertGreater(title_score, body_score)
    
    def test_field_score_headings_intermediate(self):
        """Headings matches should score between title and body."""
        title_score = self.reranker._compute_field_score(
            title="Python Tutorial",
            headings_text="",
            body_text="",
            terms=["python", "tutorial"]
        )
        headings_score = self.reranker._compute_field_score(
            title="Guide",
            headings_text="Python Tutorial Section",
            body_text="",
            terms=["python", "tutorial"]
        )
        body_score = self.reranker._compute_field_score(
            title="Guide",
            headings_text="",
            body_text="python tutorial content",
            terms=["python", "tutorial"]
        )
        self.assertGreater(title_score, headings_score)
        self.assertGreater(headings_score, body_score)
    
    def test_field_score_cumulative(self):
        """Score should be higher when terms appear in multiple fields."""
        single_field = self.reranker._compute_field_score(
            title="Python Tutorial",
            headings_text="",
            body_text="",
            terms=["python", "tutorial"]
        )
        multi_field = self.reranker._compute_field_score(
            title="Python Tutorial",
            headings_text="Python Basics",
            body_text="python tutorial guide",
            terms=["python", "tutorial"]
        )
        self.assertGreaterEqual(multi_field, single_field)
    
    def test_field_score_empty_terms(self):
        """Should return 0 for empty terms."""
        score = self.reranker._compute_field_score(
            title="Python Tutorial",
            headings_text="Section",
            body_text="content",
            terms=[]
        )
        self.assertAlmostEqual(score, 0.0)
    
    def test_field_score_normalized(self):
        """Score should be capped at field_max_score."""
        score = self.reranker._compute_field_score(
            title="Python Tutorial",
            headings_text="Python Tutorial",
            body_text="python tutorial python tutorial",
            terms=["python", "tutorial"]
        )
        self.assertLessEqual(score, self.reranker.config.field_max_score)


class TestRerankerIntegration(unittest.TestCase):
    """Integration tests for the full reranking pipeline."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def _make_doc(
        self, 
        url: str, 
        title: str, 
        score: float,
        description: str = ""
    ) -> Dict[str, Any]:
        """Helper to create a document dict."""
        return {
            'url': url,
            'title': title,
            'score': score,
            'description': description
        }
    
    def test_rerank_empty_candidates(self):
        """Should handle empty candidate list."""
        result = self.reranker.rerank(
            candidates=[],
            original_terms=["python"],
            phrases=[],
            load_text_fn=None
        )
        self.assertEqual(result, [])
    
    def test_rerank_single_candidate(self):
        """Should handle single candidate."""
        doc = self._make_doc("http://example.com", "Python Tutorial", 5.0)
        
        result = self.reranker.rerank(
            candidates=[doc],
            original_terms=["python", "tutorial"],
            phrases=[],
            load_text_fn=None
        )
        
        self.assertEqual(len(result), 1)
        self.assertIn('final_score', result[0])
    
    def test_rerank_prefers_title_match(self):
        """Documents with title matches should rank higher."""
        doc_with_title = self._make_doc(
            "http://example.com/1", 
            "Python Tutorial", 
            5.0
        )
        doc_without_title = self._make_doc(
            "http://example.com/2", 
            "Programming Guide", 
            5.0  # Same BM25 score
        )
        
        def load_text(url):
            if url.endswith("/1"):
                return "This is about python."
            return "Python tutorial content here."
        
        result = self.reranker.rerank(
            candidates=[doc_without_title, doc_with_title],
            original_terms=["python", "tutorial"],
            phrases=[],
            load_text_fn=load_text
        )
        
        # Doc with title match should be first
        self.assertEqual(result[0]['url'], "http://example.com/1")
    
    def test_rerank_prefers_full_coverage(self):
        """Documents matching all terms should rank higher."""
        doc_all_terms = self._make_doc(
            "http://example.com/1", 
            "Guide", 
            5.0
        )
        doc_one_term = self._make_doc(
            "http://example.com/2", 
            "Guide", 
            5.0
        )
        
        def load_text(url):
            if url.endswith("/1"):
                return "python list comprehension explained"
            return "python python python python python"  # Many "python" but no other terms
        
        result = self.reranker.rerank(
            candidates=[doc_one_term, doc_all_terms],
            original_terms=["python", "list", "comprehension"],
            phrases=[],
            load_text_fn=load_text
        )
        
        # Doc with all terms should be first
        self.assertEqual(result[0]['url'], "http://example.com/1")
    
    def test_rerank_respects_bm25_baseline(self):
        """Very high BM25 scores should still matter."""
        doc_low_bm25 = self._make_doc(
            "http://example.com/1", 
            "Python Tutorial", 
            1.0
        )
        doc_high_bm25 = self._make_doc(
            "http://example.com/2", 
            "Python Guide", 
            10.0  # Much higher BM25
        )
        
        def load_text(url):
            return "python tutorial content"
        
        result = self.reranker.rerank(
            candidates=[doc_low_bm25, doc_high_bm25],
            original_terms=["python", "tutorial"],
            phrases=[],
            load_text_fn=load_text
        )
        
        # High BM25 doc should still rank reasonably well
        # (may or may not be first depending on title match weight)
        high_bm25_rank = next(
            i for i, r in enumerate(result) 
            if r['url'] == "http://example.com/2"
        )
        self.assertLessEqual(high_bm25_rank, 1)  # Should be in top 2
    
    def test_rerank_adds_final_score(self):
        """Should add final_score to all candidates."""
        docs = [
            self._make_doc("http://example.com/1", "Python", 5.0),
            self._make_doc("http://example.com/2", "Guide", 4.0),
        ]
        
        result = self.reranker.rerank(
            candidates=docs,
            original_terms=["python"],
            phrases=[],
            load_text_fn=None
        )
        
        for doc in result:
            self.assertIn('final_score', doc)
            self.assertIsInstance(doc['final_score'], float)
    
    def test_rerank_top_k_limits_results(self):
        """Should respect top_k parameter."""
        docs = [
            self._make_doc(f"http://example.com/{i}", f"Doc {i}", float(i))
            for i in range(10)
        ]
        
        result = self.reranker.rerank(
            candidates=docs,
            original_terms=["doc"],
            phrases=[],
            load_text_fn=None,
            top_k=3
        )
        
        self.assertEqual(len(result), 3)
    
    def test_rerank_metrics_populated(self):
        """Should populate metrics after reranking."""
        docs = [
            self._make_doc(f"http://example.com/{i}", f"Doc {i}", float(i))
            for i in range(10)
        ]
        
        self.reranker.rerank(
            candidates=docs,
            original_terms=["doc"],
            phrases=[],
            load_text_fn=None
        )
        
        metrics = self.reranker.last_metrics
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.recall_count, 10)
        self.assertEqual(metrics.rerank_count, 10)
        self.assertIsInstance(metrics.score_components, list)


class TestRerankerWithPhrases(unittest.TestCase):
    """Tests for phrase handling in reranking."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def _make_doc(self, url: str, title: str, score: float) -> Dict[str, Any]:
        return {'url': url, 'title': title, 'score': score}
    
    def test_phrase_boost_exact_match(self):
        """Exact phrase matches should boost score."""
        doc_exact = self._make_doc("http://example.com/1", "Guide", 5.0)
        doc_no_phrase = self._make_doc("http://example.com/2", "Guide", 5.0)
        
        def load_text(url):
            if url.endswith("/1"):
                return "Learn about python tutorial basics"
            return "Python programming and tutorial videos"
        
        result = self.reranker.rerank(
            candidates=[doc_no_phrase, doc_exact],
            original_terms=["python", "tutorial"],
            phrases=[["python", "tutorial"]],
            load_text_fn=load_text
        )
        
        # Doc with exact phrase should be first
        self.assertEqual(result[0]['url'], "http://example.com/1")
    
    def test_phrase_in_title_stronger(self):
        """Phrase in title should boost more than in body."""
        doc_title_phrase = self._make_doc(
            "http://example.com/1", 
            "Python Tutorial", 
            5.0
        )
        doc_body_phrase = self._make_doc(
            "http://example.com/2", 
            "Programming Guide", 
            5.0
        )
        
        def load_text(url):
            if url.endswith("/2"):
                return "This python tutorial is great"
            return "Programming basics"
        
        result = self.reranker.rerank(
            candidates=[doc_body_phrase, doc_title_phrase],
            original_terms=["python", "tutorial"],
            phrases=[["python", "tutorial"]],
            load_text_fn=load_text
        )
        
        # Doc with phrase in title should be first
        self.assertEqual(result[0]['url'], "http://example.com/1")


class TestPhraseProximityScoring(unittest.TestCase):
    """Tests for phrase proximity scoring."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def test_exact_phrase_highest_score(self):
        """Exact phrase match should score highest."""
        exact_score = self.reranker._compute_phrase_score(
            "python tutorial guide",
            [["python", "tutorial"]],
            in_title=True
        )
        # Should get the exact match boost
        self.assertEqual(exact_score, self.reranker.config.phrase_exact_title)
    
    def test_proximity_match_medium_score(self):
        """Close proximity match should score lower than exact."""
        # Words within slop distance
        proximity_score = self.reranker._compute_phrase_score(
            "python is a tutorial",
            [["python", "tutorial"]],
            in_title=True
        )
        exact_score = self.reranker._compute_phrase_score(
            "python tutorial",
            [["python", "tutorial"]],
            in_title=True
        )
        self.assertLess(proximity_score, exact_score)
        self.assertGreater(proximity_score, 0)
    
    def test_far_apart_low_score(self):
        """Terms far apart should score lower than proximity."""
        # Very far apart (>10 words)
        far_score = self.reranker._compute_phrase_score(
            "python is a great language for programming and scripting and here is a tutorial",
            [["python", "tutorial"]],
            in_title=False
        )
        # Within slop distance
        close_score = self.reranker._compute_phrase_score(
            "python is a tutorial",  # span = 3, within slop
            [["python", "tutorial"]],
            in_title=False
        )
        self.assertLess(far_score, close_score)
    
    def test_find_min_phrase_span_exact(self):
        """Adjacent words should have span of 1."""
        span = self.reranker._find_min_phrase_span(
            "python tutorial guide",
            ["python", "tutorial"]
        )
        self.assertEqual(span, 1)
    
    def test_find_min_phrase_span_with_gap(self):
        """Words with gap should report correct span."""
        span = self.reranker._find_min_phrase_span(
            "python is a tutorial",
            ["python", "tutorial"]
        )
        self.assertEqual(span, 3)  # python(0) to tutorial(3)
    
    def test_find_min_phrase_span_missing_term(self):
        """Should return None if term is missing."""
        span = self.reranker._find_min_phrase_span(
            "python basics",
            ["python", "tutorial"]
        )
        self.assertIsNone(span)
    
    def test_body_scores_lower_than_title(self):
        """Body phrase scores should be lower than title."""
        title_score = self.reranker._compute_phrase_score(
            "python tutorial",
            [["python", "tutorial"]],
            in_title=True
        )
        body_score = self.reranker._compute_phrase_score(
            "python tutorial",
            [["python", "tutorial"]],
            in_title=False
        )
        self.assertGreater(title_score, body_score)


class TestCheckPhraseProximity(unittest.TestCase):
    """Tests for the check_phrase_proximity helper function."""
    
    def test_exact_match(self):
        """Should return True for exact phrase match."""
        self.assertTrue(check_phrase_proximity(
            "python tutorial guide",
            ["python", "tutorial"]
        ))
    
    def test_within_slop(self):
        """Should return True for terms within slop distance."""
        # Default slop is 3
        self.assertTrue(check_phrase_proximity(
            "python is a tutorial",  # span=3
            ["python", "tutorial"],
            max_slop=3
        ))
    
    def test_beyond_slop(self):
        """Should return False for terms beyond slop distance."""
        self.assertFalse(check_phrase_proximity(
            "python is a great language tutorial",  # span=5
            ["python", "tutorial"],
            max_slop=3
        ))
    
    def test_missing_term(self):
        """Should return False if a term is missing."""
        self.assertFalse(check_phrase_proximity(
            "python basics",
            ["python", "tutorial"]
        ))
    
    def test_empty_phrase(self):
        """Should return True for empty/single-word phrase."""
        self.assertTrue(check_phrase_proximity("text", []))
        self.assertTrue(check_phrase_proximity("text", ["text"]))


class TestCreateReranker(unittest.TestCase):
    """Tests for Reranker construction."""

    def test_create_default(self):
        reranker = Reranker()
        self.assertIsInstance(reranker, Reranker)
        self.assertEqual(reranker.config.recall_multiplier, 4)

    def test_create_with_config(self):
        reranker = Reranker(RerankConfig(recall_multiplier=5, weight_bm25=0.6))
        self.assertEqual(reranker.config.recall_multiplier, 5)
        self.assertAlmostEqual(reranker.config.weight_bm25, 0.6)


class TestWeightedTermExpansion(unittest.TestCase):
    """Tests for weighted term expansion in reranking."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def _make_doc(self, url: str, title: str, score: float) -> Dict[str, Any]:
        return {'url': url, 'title': title, 'score': score}
    
    def test_rerank_with_term_weights(self):
        """Should accept and use term_weights."""
        doc = self._make_doc("http://example.com", "Python Guide", 5.0)
        
        weights = {'python': 1.0, 'guide': 1.0, 'tutorial': 0.5}
        
        result = self.reranker.rerank(
            candidates=[doc],
            original_terms=["python", "guide"],
            phrases=[],
            load_text_fn=None,
            term_weights=weights
        )
        
        self.assertEqual(len(result), 1)
        self.assertIn('final_score', result[0])
    
    def test_weighted_coverage_vs_unweighted(self):
        """Weighted coverage should differ from unweighted."""
        # Document matching the lower-weight term
        doc = self._make_doc("http://example.com", "Tutorial Guide", 5.0)
        
        # Unweighted coverage
        unweighted_score = self.reranker._compute_coverage_score(
            "tutorial basics",
            ["python", "tutorial"],
            beta=0.4
        )
        
        # Weighted coverage (python=1.0, tutorial=0.3)
        weighted_score = self.reranker._compute_coverage_score(
            "tutorial basics",
            ["python", "tutorial"],
            beta=0.4,
            term_weights={"python": 1.0, "tutorial": 0.3}
        )
        
        # Weighted should be different (lower because tutorial has low weight)
        self.assertNotEqual(unweighted_score, weighted_score)


class TestBM25Normalization(unittest.TestCase):
    """Tests for BM25 score normalization."""
    
    def setUp(self):
        self.reranker = Reranker()
    
    def test_normalize_scores(self):
        """Should normalize scores to 0-1 range."""
        candidates = [
            {'score': 10.0, 'title': 'A'},
            {'score': 5.0, 'title': 'B'},
            {'score': 2.5, 'title': 'C'},
        ]
        
        self.reranker._normalize_bm25_scores(candidates)
        
        self.assertAlmostEqual(candidates[0]['_norm_bm25'], 1.0)
        self.assertAlmostEqual(candidates[1]['_norm_bm25'], 0.5)
        self.assertAlmostEqual(candidates[2]['_norm_bm25'], 0.25)
    
    def test_normalize_zero_max(self):
        """Should handle zero max score."""
        candidates = [
            {'score': 0.0, 'title': 'A'},
            {'score': 0.0, 'title': 'B'},
        ]
        
        self.reranker._normalize_bm25_scores(candidates)
        
        self.assertAlmostEqual(candidates[0]['_norm_bm25'], 0.0)
    
    def test_normalize_empty(self):
        """Should handle empty list."""
        candidates = []
        self.reranker._normalize_bm25_scores(candidates)  # Should not raise


if __name__ == '__main__':
    unittest.main()
