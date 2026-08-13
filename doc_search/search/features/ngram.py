"""
N-gram index for partial and substring matching.

Supports:
- Prefix search: "pyth*" matches "python", "pythonic"
- Substring search: "script" matches "javascript", "typescript"
- Fuzzy partial matching via trigram overlap
"""

import json
import gzip
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional


class NGramIndex:
    """
    Character n-gram index for partial term matching.
    
    Uses trigrams (3-character sequences) with word boundary markers
    to enable prefix and substring searches.
    
    Example:
        >>> idx = NGramIndex()
        >>> idx.add_term("python", frequency=100)
        >>> idx.add_term("javascript", frequency=50)
        >>> idx.search_prefix("pyth")
        [('python', 1.0, 100)]
        >>> idx.search_substring("script")
        [('javascript', 0.67, 50)]
    """
    
    # Boundary marker for word start/end
    BOUNDARY = '$'
    
    def __init__(self, n: int = 3, min_term_length: int = 3):
        """
        Initialize n-gram index.
        
        Args:
            n: Size of n-grams (default: 3 for trigrams)
            min_term_length: Minimum term length to index
        """
        self.n = n
        self.min_term_length = min_term_length
        
        # ngram → set of terms containing it
        self.ngram_to_terms: Dict[str, Set[str]] = defaultdict(set)
        
        # term → set of ngrams
        self.term_to_ngrams: Dict[str, Set[str]] = {}
        
        # term → frequency (for ranking)
        self.term_frequencies: Dict[str, int] = {}
        
        # term → position ngrams (for prefix matching)
        # Maps term → list of (position, ngram) for ordered matching
        self.term_prefix_ngrams: Dict[str, List[str]] = {}
    
    def _get_ngrams(self, term: str, with_boundaries: bool = True) -> Set[str]:
        """
        Generate n-grams from a term.
        
        Args:
            term: Term to generate n-grams from
            with_boundaries: Add boundary markers for word start/end
            
        Returns:
            Set of n-grams
        """
        term = term.lower()
        
        if with_boundaries:
            # Add boundary markers
            padded = self.BOUNDARY + term + self.BOUNDARY
        else:
            padded = term
        
        ngrams = set()
        for i in range(len(padded) - self.n + 1):
            ngrams.add(padded[i:i + self.n])
        
        return ngrams
    
    def _get_prefix_ngrams(self, term: str) -> List[str]:
        """
        Generate ordered n-grams from the start of a term (for prefix matching).
        
        Args:
            term: Term to generate prefix n-grams from
            
        Returns:
            List of n-grams in order from start
        """
        term = term.lower()
        padded = self.BOUNDARY + term
        
        ngrams = []
        for i in range(min(len(padded) - self.n + 1, len(term))):
            ngrams.append(padded[i:i + self.n])
        
        return ngrams
    
    def add_term(self, term: str, frequency: int = 1) -> None:
        """
        Add a term to the index.
        
        Args:
            term: Term to add
            frequency: Term frequency (for ranking)
        """
        term = term.lower()
        
        if len(term) < self.min_term_length:
            return
        
        # Generate and store ngrams
        ngrams = self._get_ngrams(term)
        self.term_to_ngrams[term] = ngrams
        self.term_frequencies[term] = frequency
        
        # Store prefix ngrams for ordered matching
        self.term_prefix_ngrams[term] = self._get_prefix_ngrams(term)
        
        # Update inverted index
        for ngram in ngrams:
            self.ngram_to_terms[ngram].add(term)
    
    def search_prefix(self, prefix: str, max_results: int = 20) -> List[Tuple[str, float, int]]:
        """
        Find terms that start with the given prefix.
        
        Args:
            prefix: Prefix to search for (without wildcard)
            max_results: Maximum results to return
            
        Returns:
            List of (term, similarity, frequency) tuples, sorted by similarity desc
        """
        prefix = prefix.lower()
        
        if len(prefix) < 2:
            return []
        
        # Get prefix ngrams (must be at the start)
        query_ngrams = self._get_prefix_ngrams(prefix)
        
        if not query_ngrams:
            return []
        
        # Find terms that have all prefix ngrams in the right order
        # Start with terms containing the first ngram (most restrictive)
        first_ngram = query_ngrams[0]
        if first_ngram not in self.ngram_to_terms:
            return []
        
        candidates = self.ngram_to_terms[first_ngram].copy()
        
        # Filter to terms that actually start with the prefix
        results = []
        for term in candidates:
            if term.startswith(prefix):
                # Perfect prefix match
                similarity = 1.0
                results.append((term, similarity, self.term_frequencies.get(term, 1)))
            elif len(query_ngrams) > 1:
                # Check if term has all query ngrams at the start
                term_prefix = self.term_prefix_ngrams.get(term, [])
                if all(qn in term_prefix[:len(query_ngrams)+1] for qn in query_ngrams):
                    # Partial prefix match
                    similarity = len(prefix) / len(term)
                    results.append((term, similarity, self.term_frequencies.get(term, 1)))
        
        # Sort by similarity (desc), then frequency (desc)
        results.sort(key=lambda x: (-x[1], -x[2]))
        
        return results[:max_results]
    
    def search_substring(self, query: str, max_results: int = 20, 
                         min_similarity: float = 0.3) -> List[Tuple[str, float, int]]:
        """
        Find terms containing the query as a substring (via n-gram overlap).
        
        Args:
            query: Substring to search for
            max_results: Maximum results to return
            min_similarity: Minimum Jaccard similarity threshold
            
        Returns:
            List of (term, similarity, frequency) tuples, sorted by similarity desc
        """
        query = query.lower()
        
        if len(query) < self.min_term_length:
            return []
        
        # Get query ngrams (without boundary markers for substring)
        query_ngrams = self._get_ngrams(query, with_boundaries=False)
        
        if not query_ngrams:
            return []
        
        # Find candidate terms (those sharing at least one ngram)
        candidate_counts: Dict[str, int] = defaultdict(int)
        for ngram in query_ngrams:
            if ngram in self.ngram_to_terms:
                for term in self.ngram_to_terms[ngram]:
                    candidate_counts[term] += 1
        
        # Calculate Jaccard similarity for each candidate
        results = []
        for term, shared_count in candidate_counts.items():
            term_ngrams = self.term_to_ngrams.get(term, set())
            
            # Jaccard similarity: |A ∩ B| / |A ∪ B|
            union_size = len(query_ngrams | term_ngrams)
            if union_size == 0:
                continue
            
            similarity = shared_count / union_size
            
            # Also check for actual substring containment (boost score)
            if query in term:
                similarity = max(similarity, 0.8)  # Boost actual substrings
            
            if similarity >= min_similarity:
                results.append((term, similarity, self.term_frequencies.get(term, 1)))
        
        # Sort by similarity (desc), then frequency (desc)
        results.sort(key=lambda x: (-x[1], -x[2]))
        
        return results[:max_results]
    
    def search(self, query: str, max_results: int = 20) -> List[Tuple[str, float, int]]:
        """
        Search for terms matching the query.
        
        Handles both prefix (ends with *) and substring queries.
        
        Args:
            query: Search query (use * suffix for prefix search)
            max_results: Maximum results to return
            
        Returns:
            List of (term, similarity, frequency) tuples
        """
        query = query.lower().strip()
        
        if query.endswith('*'):
            # Prefix search
            prefix = query[:-1]
            return self.search_prefix(prefix, max_results)
        else:
            # Substring search
            return self.search_substring(query, max_results)
    
    def get_stats(self) -> Dict:
        """Get index statistics."""
        return {
            'term_count': len(self.term_to_ngrams),
            'ngram_count': len(self.ngram_to_terms),
            'n': self.n,
            'min_term_length': self.min_term_length,
        }
    
    def save(self, path: str, compress: bool = True) -> str:
        """
        Save the n-gram index to a file.
        
        Args:
            path: Base path (without extension)
            compress: Whether to gzip compress
            
        Returns:
            Actual path written
        """
        data = {
            'version': 1,
            'n': self.n,
            'min_term_length': self.min_term_length,
            'term_frequencies': self.term_frequencies,
            'term_to_ngrams': {k: list(v) for k, v in self.term_to_ngrams.items()},
            'term_prefix_ngrams': self.term_prefix_ngrams,
        }
        
        if compress:
            out_path = f"{path}.json.gz"
            with gzip.open(out_path, 'wt', encoding='utf-8') as f:
                json.dump(data, f)
        else:
            out_path = f"{path}.json"
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        
        return out_path
    
    @classmethod
    def load(cls, path: str) -> 'NGramIndex':
        """
        Load an n-gram index from a file.
        
        Args:
            path: Path to the index file
            
        Returns:
            Loaded NGramIndex instance
        """
        if path.endswith('.gz'):
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        instance = cls(
            n=data.get('n', 3),
            min_term_length=data.get('min_term_length', 3)
        )
        
        instance.term_frequencies = data['term_frequencies']
        instance.term_to_ngrams = {k: set(v) for k, v in data['term_to_ngrams'].items()}
        instance.term_prefix_ngrams = data['term_prefix_ngrams']
        
        # Rebuild inverted index
        for term, ngrams in instance.term_to_ngrams.items():
            for ngram in ngrams:
                instance.ngram_to_terms[ngram].add(term)
        
        return instance
