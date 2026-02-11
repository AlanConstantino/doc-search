"""
Two-stage retrieval reranking module.

This module provides reranking functionality that combines multiple signals
to produce better search rankings than BM25 alone.

Architecture:
    Query → [Stage 1: Recall] → Candidates → [Stage 2: Rerank] → Results
               (fast, broad)                    (precise ranking)

Stage 1 (Recall):
    - Fast inverted index lookup using BM25
    - Casts wide net with expanded terms
    - Returns large candidate set (e.g., 100-500 docs)

Stage 2 (Rerank):
    - Combines multiple ranking signals
    - Title/field boosting
    - Query term coverage
    - Phrase proximity
    - Returns final ranked list
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field

from .constants import (
    RERANK_WEIGHT_BM25,
    RERANK_WEIGHT_FIELD,
    RERANK_WEIGHT_COVERAGE,
    RERANK_WEIGHT_PHRASE,
    RERANK_COVERAGE_BETA,
    RERANK_TITLE_COVERAGE_BETA,
    RERANK_FULL_COVERAGE_BONUS,
    RERANK_MAX_COVERAGE_TERMS,
    RERANK_RECALL_MULTIPLIER,
    RERANK_MAX_CANDIDATES,
    RERANK_CANDIDATE_LIMIT,
    FIELD_WEIGHT_TITLE,
    FIELD_WEIGHT_HEADINGS,
    FIELD_WEIGHT_BODY,
    FIELD_MAX_SCORE,
    PHRASE_MAX_SLOP,
    PHRASE_EXACT_MATCH_TITLE,
    PHRASE_EXACT_MATCH_BODY,
    PHRASE_PROXIMITY_MATCH_TITLE,
    PHRASE_PROXIMITY_MATCH_BODY,
)


@dataclass
class RerankConfig:
    """
    Configuration for the reranking stage.
    
    Attributes:
        recall_multiplier: Fetch this multiple of top_k in recall stage
        max_candidates: Maximum candidates to fetch in recall stage
        candidate_limit: Maximum candidates to rerank (for performance)
        weight_bm25: Weight for base BM25 score
        weight_field: Weight for field-aware term matching
        weight_coverage: Weight for query term coverage
        weight_phrase: Weight for phrase/proximity matches
        field_weight_title: Weight multiplier for title field
        field_weight_headings: Weight multiplier for headings field
        field_weight_body: Weight multiplier for body field
        coverage_beta: Strength of coverage boost
        title_coverage_beta: Strength of title-specific coverage boost
        full_coverage_bonus: Extra bonus when all terms are present
        max_coverage_terms: Maximum terms to consider for coverage scoring
    """
    recall_multiplier: int = RERANK_RECALL_MULTIPLIER
    max_candidates: int = RERANK_MAX_CANDIDATES
    candidate_limit: int = RERANK_CANDIDATE_LIMIT
    weight_bm25: float = RERANK_WEIGHT_BM25
    weight_field: float = RERANK_WEIGHT_FIELD
    weight_coverage: float = RERANK_WEIGHT_COVERAGE
    weight_phrase: float = RERANK_WEIGHT_PHRASE
    field_weight_title: float = FIELD_WEIGHT_TITLE
    field_weight_headings: float = FIELD_WEIGHT_HEADINGS
    field_weight_body: float = FIELD_WEIGHT_BODY
    field_max_score: float = FIELD_MAX_SCORE
    coverage_beta: float = RERANK_COVERAGE_BETA
    title_coverage_beta: float = RERANK_TITLE_COVERAGE_BETA
    full_coverage_bonus: float = RERANK_FULL_COVERAGE_BONUS
    max_coverage_terms: int = RERANK_MAX_COVERAGE_TERMS
    # Phrase proximity settings
    phrase_max_slop: int = PHRASE_MAX_SLOP
    phrase_exact_title: float = PHRASE_EXACT_MATCH_TITLE
    phrase_exact_body: float = PHRASE_EXACT_MATCH_BODY
    phrase_proximity_title: float = PHRASE_PROXIMITY_MATCH_TITLE
    phrase_proximity_body: float = PHRASE_PROXIMITY_MATCH_BODY


@dataclass
class RerankMetrics:
    """
    Metrics from reranking for debugging and tuning.
    
    Attributes:
        recall_count: Number of candidates from recall stage
        rerank_count: Number of candidates actually reranked
        score_components: Breakdown of score components for top results
    """
    recall_count: int = 0
    rerank_count: int = 0
    score_components: List[Dict[str, float]] = field(default_factory=list)


class Reranker:
    """
    Reranks search results using multiple signals.
    
    This class combines BM25 scores with additional ranking signals:
    - Title/heading term matches (field-aware ranking)
    - Query term coverage (reward matching more query terms)
    - Phrase proximity (terms appearing close together)
    
    Example:
        >>> reranker = Reranker()
        >>> reranked = reranker.rerank(
        ...     candidates=bm25_results,
        ...     original_terms=['python', 'tutorial'],
        ...     phrases=[['python', 'tutorial']],
        ...     load_text_fn=load_page_text
        ... )
    """
    
    def __init__(self, config: Optional[RerankConfig] = None):
        """
        Initialize the reranker.
        
        Args:
            config: Reranking configuration. Uses defaults if not provided.
        """
        self.config = config or RerankConfig()
        self._last_metrics: Optional[RerankMetrics] = None
    
    @property
    def last_metrics(self) -> Optional[RerankMetrics]:
        """Get metrics from the last rerank() call."""
        return self._last_metrics
    
    def compute_recall_k(self, top_k: int) -> int:
        """
        Compute how many candidates to fetch in recall stage.
        
        Args:
            top_k: Final number of results requested
            
        Returns:
            Number of candidates to fetch (bounded by max_candidates)
        """
        return min(top_k * self.config.recall_multiplier, self.config.max_candidates)
    
    def _normalize_bm25_scores(self, candidates: List[Dict[str, Any]]) -> None:
        """
        Normalize BM25 scores to 0-1 range in place.
        
        This allows fair combination with other signals.
        """
        if not candidates:
            return
        
        max_score = max(c.get('score', 0) for c in candidates)
        if max_score > 0:
            for c in candidates:
                c['_norm_bm25'] = c.get('score', 0) / max_score
        else:
            for c in candidates:
                c['_norm_bm25'] = 0.0
    
    def _compute_term_matches(
        self, 
        text: str, 
        terms: List[str]
    ) -> float:
        """
        Compute the fraction of query terms that match in text.
        
        Args:
            text: Text to search in
            terms: Query terms to match
            
        Returns:
            Normalized score (0-1) based on term matches
        """
        if not text or not terms:
            return 0.0
        
        text_lower = text.lower()
        matches = sum(1 for term in terms if term.lower() in text_lower)
        
        # Normalize by number of query terms
        return matches / len(terms)
    
    def _compute_field_score(
        self,
        title: str,
        headings_text: str,
        body_text: Optional[str],
        terms: List[str]
    ) -> float:
        """
        Compute field-aware score based on where query terms appear.
        
        Fields are weighted: title > headings > body
        A term appearing in the title is worth more than in headings,
        which is worth more than in body text.
        
        Args:
            title: Document title
            headings_text: Concatenated heading text (h1, h2, etc.)
            body_text: Full document body text
            terms: Original query terms
            
        Returns:
            Normalized field score (0-1)
        """
        if not terms:
            return 0.0
        
        # Calculate weighted score for each field
        title_matches = self._compute_term_matches(title, terms)
        headings_matches = self._compute_term_matches(headings_text, terms)
        body_matches = self._compute_term_matches(body_text or '', terms)
        
        # Weight by field importance
        # Each term can only contribute once - use max across fields weighted
        total_weight = (
            self.config.field_weight_title + 
            self.config.field_weight_headings + 
            self.config.field_weight_body
        )
        
        weighted_score = (
            title_matches * self.config.field_weight_title +
            headings_matches * self.config.field_weight_headings +
            body_matches * self.config.field_weight_body
        ) / total_weight
        
        # Cap at field_max_score
        return min(weighted_score, self.config.field_max_score)
    
    def _compute_coverage_score(
        self, 
        text: str, 
        terms: List[str],
        beta: float,
        term_weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Compute coverage boost based on how many query terms are matched.
        
        Formula: 1 + β * coverage
        - coverage=1.0 (all terms) → boost = 1 + β
        - coverage=0.5 (half terms) → boost = 1 + 0.5β
        - coverage=0.0 (no terms) → boost = 1 (no boost)
        
        For very long queries, only considers max_coverage_terms most important
        terms to prevent dilution of the coverage signal.
        
        Args:
            text: Document text to check
            terms: Original query terms (not expanded)
            beta: Boost strength (typically 0.2-0.6)
            term_weights: Optional dict of term -> weight for weighted coverage
            
        Returns:
            Multiplier >= 1.0
        """
        if not terms or not text:
            return 1.0
        
        # For long queries, limit terms considered
        coverage_terms = terms
        if len(terms) > self.config.max_coverage_terms:
            if term_weights:
                # Sort by weight and take top N
                coverage_terms = sorted(
                    terms, 
                    key=lambda t: term_weights.get(t.lower(), 0), 
                    reverse=True
                )[:self.config.max_coverage_terms]
            else:
                # Without weights, just take first N
                coverage_terms = terms[:self.config.max_coverage_terms]
        
        text_lower = text.lower()
        
        if term_weights:
            # Weighted coverage: weight matches by term importance
            matched_weight = sum(
                term_weights.get(term.lower(), 1.0)
                for term in coverage_terms
                if term.lower() in text_lower
            )
            total_weight = sum(
                term_weights.get(term.lower(), 1.0)
                for term in coverage_terms
            )
            coverage = matched_weight / total_weight if total_weight > 0 else 0
        else:
            # Simple coverage: count matching terms
            matched = sum(1 for term in coverage_terms if term.lower() in text_lower)
            coverage = matched / len(coverage_terms)
        
        # Add bonus for full coverage
        bonus = self.config.full_coverage_bonus if coverage == 1.0 else 0.0
        
        return 1.0 + (beta * coverage) + bonus
    
    def _compute_weighted_coverage(
        self,
        text: str,
        terms: List[str],
        term_weights: Dict[str, float]
    ) -> float:
        """
        Compute coverage weighted by term importance.
        
        This is useful when some query terms are more important than others
        (e.g., original terms vs expanded/synonym terms).
        
        Args:
            text: Document text to check
            terms: Query terms
            term_weights: Dict mapping term -> importance weight
            
        Returns:
            Weighted coverage ratio (0-1)
        """
        if not terms or not text:
            return 0.0
        
        text_lower = text.lower()
        
        matched_weight = sum(
            term_weights.get(term.lower(), 1.0)
            for term in terms
            if term.lower() in text_lower
        )
        total_weight = sum(
            term_weights.get(term.lower(), 1.0)
            for term in terms
        )
        
        return matched_weight / total_weight if total_weight > 0 else 0.0
    
    def _compute_phrase_score(
        self, 
        text: str, 
        phrases: List[List[str]],
        in_title: bool = False
    ) -> float:
        """
        Score phrase matches with field-aware boosting and proximity.
        
        Scoring levels:
        1. Exact phrase match → highest boost
        2. Proximity match (within slop) → medium boost
        3. All terms present but far apart → low boost
        
        Args:
            text: Text to search in
            phrases: List of phrase word lists
            in_title: Whether this is title text (higher boost)
            
        Returns:
            Phrase match score (unnormalized)
        """
        if not phrases or not text:
            return 0.0
        
        text_lower = text.lower()
        score = 0.0
        
        # Select boost values based on field
        exact_boost = self.config.phrase_exact_title if in_title else self.config.phrase_exact_body
        proximity_boost = self.config.phrase_proximity_title if in_title else self.config.phrase_proximity_body
        
        for phrase in phrases:
            if len(phrase) < 2:
                continue
            
            phrase_str = ' '.join(phrase).lower()
            
            # Check for exact phrase match (highest score)
            if phrase_str in text_lower:
                score += exact_boost
            else:
                # Check for proximity match with slop
                min_span = self._find_min_phrase_span(text_lower, phrase)
                
                if min_span is not None:
                    if min_span <= self.config.phrase_max_slop:
                        # Close proximity - good match
                        # Score decreases as span increases
                        proximity_factor = 1.0 - (min_span / (self.config.phrase_max_slop + 1))
                        score += proximity_boost * proximity_factor
                    elif min_span <= 10:
                        # Moderate proximity - okay match
                        score += proximity_boost * 0.3
                    else:
                        # Far apart - minimal score
                        score += proximity_boost * 0.1
        
        return score
    
    def _find_min_phrase_span(
        self,
        text: str,
        phrase_words: List[str]
    ) -> Optional[int]:
        """
        Find the minimum word span containing all phrase terms.
        
        Args:
            text: Lowercase text to search
            phrase_words: Words that should appear close together
            
        Returns:
            Minimum span (number of words between first and last term),
            or None if not all terms are found
        """
        if len(phrase_words) < 2:
            return 0
        
        # Find positions of each term
        words = text.split()
        term_positions: Dict[str, List[int]] = {}
        
        for i, word in enumerate(words):
            clean_word = re.sub(r'[^\w]', '', word.lower())
            for term in phrase_words:
                term_lower = term.lower()
                if term_lower in clean_word or clean_word == term_lower:
                    if term not in term_positions:
                        term_positions[term] = []
                    term_positions[term].append(i)
        
        # Check if all terms were found
        if len(term_positions) < len(phrase_words):
            return None
        
        # Find minimum span containing all terms
        all_positions = []
        for term, positions in term_positions.items():
            all_positions.extend((pos, term) for pos in positions)
        
        if not all_positions:
            return None
        
        all_positions.sort()
        
        min_span = float('inf')
        term_set = set(phrase_words)
        
        for i in range(len(all_positions)):
            found_terms = set()
            for j in range(i, len(all_positions)):
                found_terms.add(all_positions[j][1])
                if found_terms >= term_set:
                    span = all_positions[j][0] - all_positions[i][0]
                    min_span = min(min_span, span)
                    break
        
        return min_span if min_span != float('inf') else None
    
    def _score_proximity(
        self, 
        text: str, 
        phrase_words: List[str],
        max_window: int = 10
    ) -> float:
        """
        Score based on how close phrase terms appear to each other.
        
        Uses _find_min_phrase_span to find the minimum span,
        then converts to a 0-1 score.
        
        Args:
            text: Lowercase text to search
            phrase_words: Words that should appear close together
            max_window: Maximum word distance to consider
            
        Returns:
            Proximity score (0-1), higher means terms are closer
        """
        if len(phrase_words) < 2:
            return 0.0
        
        min_span = self._find_min_phrase_span(text, phrase_words)
        
        if min_span is None or min_span > max_window:
            return 0.0
        
        # Convert span to score (closer = higher)
        # span=0 (adjacent) → score=1.0
        # span=max_window → score=0.0
        return 1.0 - (min_span / max_window)
    
    def compute_rerank_score(
        self,
        doc: Dict[str, Any],
        body_text: Optional[str],
        original_terms: List[str],
        phrases: List[List[str]],
        headings_text: Optional[str] = None,
        term_weights: Optional[Dict[str, float]] = None
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute the final rerank score for a document.
        
        Combines multiple signals:
        - Normalized BM25 score (from recall stage)
        - Field-aware term matches (title > headings > body)
        - Query term coverage (optionally weighted by term importance)
        - Phrase/proximity matches
        
        Args:
            doc: Document dict with 'score', 'title', 'headings_text', etc.
            body_text: Full document text (or None)
            original_terms: Original query terms (not expanded)
            phrases: Phrase groups from query
            headings_text: Concatenated heading text (optional, falls back to doc)
            term_weights: Optional dict of term -> weight for weighted coverage
            
        Returns:
            Tuple of (final_score, score_components_dict)
        """
        title = doc.get('title', '') or ''
        # Get headings from doc metadata if not provided
        if headings_text is None:
            headings_text = doc.get('headings_text', '') or ''
        
        # Get normalized BM25 score (set by _normalize_bm25_scores)
        bm25_score = doc.get('_norm_bm25', 0.0)
        
        # Field-aware score (title > headings > body)
        field_score = self._compute_field_score(
            title=title,
            headings_text=headings_text,
            body_text=body_text,
            terms=original_terms
        )
        
        # Coverage scores (optionally weighted by term importance)
        body_coverage = 1.0
        title_coverage = 1.0
        
        if original_terms:
            if body_text:
                body_coverage = self._compute_coverage_score(
                    body_text, original_terms, self.config.coverage_beta,
                    term_weights=term_weights
                )
            title_coverage = self._compute_coverage_score(
                title, original_terms, self.config.title_coverage_beta,
                term_weights=term_weights
            )
        
        # Phrase scores
        phrase_score = 0.0
        if phrases:
            phrase_score += self._compute_phrase_score(title, phrases, in_title=True)
            if headings_text:
                # Headings phrase match is between title and body
                phrase_score += self._compute_phrase_score(headings_text, phrases, in_title=False) * 1.5
            if body_text:
                phrase_score += self._compute_phrase_score(body_text, phrases, in_title=False)
            # Normalize phrase score (cap at 1.0)
            phrase_score = min(1.0, phrase_score)
        
        # Combine scores with weights
        weighted_score = (
            bm25_score * self.config.weight_bm25 +
            field_score * self.config.weight_field +
            phrase_score * self.config.weight_phrase
        )
        
        # Apply coverage as a multiplier (not additive)
        # This ensures documents matching more terms get boosted
        coverage_multiplier = body_coverage * title_coverage
        weighted_score *= coverage_multiplier
        
        # Add coverage component for transparency
        # (coverage effect is multiplicative, but we log the raw coverage for debugging)
        avg_coverage = (body_coverage + title_coverage) / 2 - 1.0  # Normalize to 0-based
        
        components = {
            'bm25': bm25_score * self.config.weight_bm25,
            'field': field_score * self.config.weight_field,
            'coverage': avg_coverage * self.config.weight_coverage,
            'phrase': phrase_score * self.config.weight_phrase,
            'coverage_multiplier': coverage_multiplier,
        }
        
        return weighted_score, components
    
    def rerank(
        self,
        candidates: List[Dict[str, Any]],
        original_terms: List[str],
        phrases: List[List[str]],
        load_text_fn: Optional[callable] = None,
        top_k: Optional[int] = None,
        term_weights: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank candidates using multiple signals.
        
        Args:
            candidates: BM25 search results from recall stage
            original_terms: Original query terms (not expanded)
            phrases: Phrase groups extracted from query
            load_text_fn: Function to load page text given URL
            top_k: Maximum results to return (None = all)
            term_weights: Optional dict of term -> weight for weighted scoring
            
        Returns:
            Reranked list of results with 'final_score' added
        """
        if not candidates:
            return []
        
        # Initialize metrics
        self._last_metrics = RerankMetrics(
            recall_count=len(candidates),
            rerank_count=0,
            score_components=[]
        )
        
        # Limit candidates to rerank for performance
        rerank_candidates = candidates[:self.config.candidate_limit]
        self._last_metrics.rerank_count = len(rerank_candidates)
        
        # Normalize BM25 scores
        self._normalize_bm25_scores(rerank_candidates)
        
        # Compute rerank scores
        for doc in rerank_candidates:
            # Load body text if we have a loader
            body_text = None
            if load_text_fn:
                body_text = load_text_fn(doc.get('url', ''))
            
            final_score, components = self.compute_rerank_score(
                doc=doc,
                body_text=body_text,
                original_terms=original_terms,
                phrases=phrases,
                term_weights=term_weights
            )
            
            doc['final_score'] = final_score
            doc['_rerank_components'] = components
        
        # Sort by final score
        rerank_candidates.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        
        # Store top score components for metrics
        self._last_metrics.score_components = [
            doc.get('_rerank_components', {})
            for doc in rerank_candidates[:5]
        ]
        
        # Return top_k if specified
        if top_k is not None:
            return rerank_candidates[:top_k]
        return rerank_candidates


def check_phrase_proximity(
    text: str, 
    phrase_words: List[str],
    max_slop: int = PHRASE_MAX_SLOP
) -> bool:
    """
    Check if phrase words appear in text within the allowed slop.
    
    This is a softer version of exact phrase matching that allows
    some words between phrase terms.
    
    Args:
        text: Text to search in
        phrase_words: Words that should appear close together
        max_slop: Maximum word distance allowed between terms
        
    Returns:
        True if all phrase words appear within the slop window
    """
    if not phrase_words or len(phrase_words) < 2:
        return True
    
    if not text:
        return False
    
    reranker = Reranker()
    min_span = reranker._find_min_phrase_span(text.lower(), phrase_words)
    
    return min_span is not None and min_span <= max_slop


def create_reranker(config: Optional[Dict[str, Any]] = None) -> Reranker:
    """
    Factory function to create a Reranker with custom config.
    
    Args:
        config: Optional dict with config overrides
        
    Returns:
        Configured Reranker instance
    """
    if config:
        rerank_config = RerankConfig(**config)
    else:
        rerank_config = RerankConfig()
    return Reranker(rerank_config)
