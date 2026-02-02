"""
Spell checking and "Did you mean..." suggestions using edit distance.

Pure Python implementation using Levenshtein distance.
"""

from typing import List, Dict, Set, Tuple, Optional

from .constants import DEFAULT_MAX_EDIT_DISTANCE, DEFAULT_MAX_SUGGESTIONS


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate the Levenshtein (edit) distance between two strings.
    
    Uses dynamic programming with O(min(m,n)) space complexity.
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        Minimum number of single-character edits (insertions, deletions,
        substitutions) required to transform s1 into s2.
    """
    # Ensure s1 is the shorter string for space efficiency
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    
    m, n = len(s1), len(s2)
    
    # Previous and current row of distances
    prev_row = list(range(m + 1))
    curr_row = [0] * (m + 1)
    
    for j in range(1, n + 1):
        curr_row[0] = j
        for i in range(1, m + 1):
            if s1[i - 1] == s2[j - 1]:
                curr_row[i] = prev_row[i - 1]
            else:
                curr_row[i] = 1 + min(
                    prev_row[i],      # deletion
                    curr_row[i - 1],  # insertion
                    prev_row[i - 1]   # substitution
                )
        prev_row, curr_row = curr_row, prev_row
    
    return prev_row[m]


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Damerau-Levenshtein distance (allows transpositions).
    
    This is more suitable for typo detection since adjacent character
    swaps (e.g., "teh" -> "the") count as one edit.
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        Minimum number of edits including transpositions.
    """
    m, n = len(s1), len(s2)
    
    # Create distance matrix
    d = [[0] * (n + 1) for _ in range(m + 1)]
    
    # Initialize first row and column
    for i in range(m + 1):
        d[i][0] = i
    for j in range(n + 1):
        d[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            
            d[i][j] = min(
                d[i - 1][j] + 1,      # deletion
                d[i][j - 1] + 1,      # insertion
                d[i - 1][j - 1] + cost  # substitution
            )
            
            # Check for transposition
            if (i > 1 and j > 1 and 
                s1[i - 1] == s2[j - 2] and 
                s1[i - 2] == s2[j - 1]):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)
    
    return d[m][n]


class SpellChecker:
    """
    Spell checker that suggests corrections based on a vocabulary.
    
    Uses Damerau-Levenshtein distance to find similar words.
    """
    
    def __init__(self, vocabulary: Set[str], max_distance: int = DEFAULT_MAX_EDIT_DISTANCE):
        """
        Initialize spell checker with vocabulary.
        
        Args:
            vocabulary: Set of known correct words
            max_distance: Maximum edit distance for suggestions
        """
        self.vocabulary = vocabulary
        self.max_distance = max_distance
        
        # Build prefix index for faster lookups
        self._prefix_index: Dict[str, Set[str]] = {}
        self._build_prefix_index()
    
    def _build_prefix_index(self):
        """Build prefix index for faster candidate generation."""
        for word in self.vocabulary:
            # Index by first 2 characters (or whole word if shorter)
            prefix = word[:2] if len(word) >= 2 else word
            if prefix not in self._prefix_index:
                self._prefix_index[prefix] = set()
            self._prefix_index[prefix].add(word)
    
    def _get_candidates(self, word: str) -> Set[str]:
        """
        Get candidate words that might be close to the given word.
        
        Uses prefix matching and length filtering to reduce comparisons.
        """
        candidates = set()
        word_len = len(word)
        
        # Get words with similar prefixes
        prefix = word[:2] if len(word) >= 2 else word
        
        # Also check nearby prefixes (for typos in first 2 chars)
        prefixes_to_check = {prefix}
        if len(prefix) >= 2:
            # Add prefixes with one char changed
            for c in 'abcdefghijklmnopqrstuvwxyz':
                prefixes_to_check.add(c + prefix[1])
                prefixes_to_check.add(prefix[0] + c)
                prefixes_to_check.add(c + prefix[0])  # transposition
        
        for p in prefixes_to_check:
            if p in self._prefix_index:
                for candidate in self._prefix_index[p]:
                    # Filter by length (can't be too different)
                    if abs(len(candidate) - word_len) <= self.max_distance:
                        candidates.add(candidate)
        
        return candidates
    
    def is_valid(self, word: str) -> bool:
        """Check if a word is in the vocabulary."""
        return word.lower() in self.vocabulary
    
    def suggest(self, word: str, max_suggestions: int = DEFAULT_MAX_SUGGESTIONS) -> List[Tuple[str, int]]:
        """
        Get spelling suggestions for a word.
        
        Args:
            word: Word to find suggestions for
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of (suggested_word, distance) tuples, sorted by distance
        """
        word = word.lower()
        
        # If word is valid, no suggestions needed
        if word in self.vocabulary:
            return []
        
        suggestions = []
        candidates = self._get_candidates(word)
        
        for candidate in candidates:
            distance = damerau_levenshtein_distance(word, candidate)
            if distance <= self.max_distance:
                suggestions.append((candidate, distance))
        
        # Sort by distance, then alphabetically
        suggestions.sort(key=lambda x: (x[1], x[0]))
        
        return suggestions[:max_suggestions]
    
    def suggest_query(self, query_terms: List[str]) -> Optional[Tuple[List[str], str]]:
        """
        Suggest corrections for a list of query terms.
        
        Args:
            query_terms: List of query terms to check
            
        Returns:
            Tuple of (corrected_terms, suggestion_string) or None if no corrections
        """
        corrections = []
        has_correction = False
        
        for term in query_terms:
            if self.is_valid(term):
                corrections.append(term)
            else:
                suggestions = self.suggest(term, max_suggestions=1)
                if suggestions:
                    corrected, _ = suggestions[0]
                    corrections.append(corrected)
                    has_correction = True
                else:
                    corrections.append(term)
        
        if has_correction:
            return corrections, ' '.join(corrections)
        
        return None
    
    def get_vocabulary_size(self) -> int:
        """Return the size of the vocabulary."""
        return len(self.vocabulary)
