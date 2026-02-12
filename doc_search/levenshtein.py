"""
Levenshtein Automaton for efficient fuzzy string matching.

A Levenshtein automaton is a finite automaton that accepts all strings
within a given edit distance of a target string. This is more efficient
than computing edit distance for every term in a vocabulary.

Algorithm:
1. Build NFA states representing (position, errors) pairs
2. Convert to DFA for efficient matching
3. Walk DFA while iterating vocabulary (or trie) to find matches

Time Complexity:
- Build: O(|pattern| * max_distance)
- Match single word: O(|word|)
- Find all matches in vocabulary: O(|vocab| * avg_word_len) with early termination

References:
- Schulz & Mihov (2002): "Fast String Correction with Levenshtein-Automata"
- https://julesjacobs.com/2015/06/17/disqus-levenshtein-simple-and-fast.html
"""

from typing import Dict, List, Set, Tuple, Optional, Iterator
from dataclasses import dataclass
from collections import defaultdict


@dataclass(frozen=True)
class State:
    """
    NFA state representing (position in pattern, number of errors).
    
    A state (i, e) means we've matched up to position i in the pattern
    with e errors so far.
    """
    position: int
    errors: int
    
    def __repr__(self) -> str:
        return f"S({self.position},{self.errors})"


class LevenshteinAutomaton:
    """
    Levenshtein automaton for finding all strings within edit distance k.
    
    Uses a lazy DFA construction approach - states are computed on demand
    as we traverse the automaton with input characters.
    
    Example:
        >>> auto = LevenshteinAutomaton("test", max_distance=1)
        >>> auto.accepts("test")   # exact match
        True
        >>> auto.accepts("tests")  # 1 insertion
        True
        >>> auto.accepts("tset")   # 1 transposition
        True
        >>> auto.accepts("best")   # 1 substitution
        True
        >>> auto.accepts("hello")  # too many errors
        False
    """
    
    def __init__(self, pattern: str, max_distance: int = 1):
        """
        Initialize automaton for a pattern with maximum edit distance.
        
        Args:
            pattern: Target string to match against
            max_distance: Maximum allowed edit distance (default: 1)
        """
        self.pattern = pattern.lower()
        self.max_distance = max_distance
        self.pattern_len = len(self.pattern)
        
        # Cache for DFA state transitions
        self._transition_cache: Dict[Tuple[frozenset, str], frozenset] = {}
        
        # Initial NFA state set
        self._initial_states = self._get_initial_states()
    
    def _get_initial_states(self) -> frozenset:
        """Get initial NFA state set (includes epsilon transitions for insertions)."""
        states = set()
        # Start at position 0 with 0 errors
        states.add(State(0, 0))
        # Can also start with up to max_distance insertions (skip pattern chars)
        for e in range(1, self.max_distance + 1):
            for i in range(e + 1):
                if i <= self.pattern_len:
                    states.add(State(i, e))
        return frozenset(states)
    
    def _step(self, states: frozenset, char: str) -> frozenset:
        """
        Compute next state set given current states and input character.
        
        Handles:
        - Match: move forward with no error cost
        - Substitution: move forward with +1 error
        - Insertion: stay at same position with +1 error  
        - Deletion: skip pattern char(s), then consume input
        
        Args:
            states: Current set of NFA states
            char: Input character to process
            
        Returns:
            New set of reachable NFA states
        """
        # Check cache first
        cache_key = (states, char)
        if cache_key in self._transition_cache:
            return self._transition_cache[cache_key]
        
        char = char.lower()
        next_states = set()
        
        # First, expand states with epsilon transitions (deletions)
        # Deletions skip pattern chars without consuming input
        expanded_states = set(states)
        for state in states:
            pos, errors = state.position, state.errors
            # Add states reachable by deleting pattern characters
            remaining_budget = self.max_distance - errors
            for d in range(1, remaining_budget + 1):
                if pos + d <= self.pattern_len:
                    expanded_states.add(State(pos + d, errors + d))
        
        # Now process input character from all expanded states
        for state in expanded_states:
            pos, errors = state.position, state.errors
            
            # Skip if over error budget
            if errors > self.max_distance:
                continue
            
            # Case 1: Match - advance position, no error cost
            if pos < self.pattern_len and self.pattern[pos] == char:
                next_states.add(State(pos + 1, errors))
            
            # Case 2: Substitution - advance position, +1 error
            if errors < self.max_distance and pos < self.pattern_len and self.pattern[pos] != char:
                next_states.add(State(pos + 1, errors + 1))
            
            # Case 3: Insertion in input - stay at same position, +1 error
            if errors < self.max_distance:
                next_states.add(State(pos, errors + 1))
        
        result = frozenset(next_states)
        self._transition_cache[cache_key] = result
        return result
    
    def _is_accepting(self, states: frozenset) -> bool:
        """Check if any state in the set is an accepting state."""
        for state in states:
            # Accept if we've matched the entire pattern within error budget
            remaining = self.pattern_len - state.position
            if state.errors + remaining <= self.max_distance:
                return True
        return False
    
    def _can_match(self, states: frozenset) -> bool:
        """Check if it's still possible to reach an accepting state."""
        return len(states) > 0
    
    def accepts(self, word: str) -> bool:
        """
        Check if a word is within edit distance of the pattern.
        
        Args:
            word: String to check
            
        Returns:
            True if edit_distance(word, pattern) <= max_distance
        """
        states = self._initial_states
        
        for char in word.lower():
            states = self._step(states, char)
            if not self._can_match(states):
                return False
        
        return self._is_accepting(states)
    
    def get_distance(self, word: str) -> Optional[int]:
        """
        Get the edit distance if within max_distance, None otherwise.
        
        Args:
            word: String to check
            
        Returns:
            Edit distance if <= max_distance, None otherwise
        """
        states = self._initial_states
        
        for char in word.lower():
            states = self._step(states, char)
            if not self._can_match(states):
                return None
        
        # Find minimum errors in accepting states
        min_distance = None
        for state in states:
            remaining = self.pattern_len - state.position
            total_errors = state.errors + remaining
            if total_errors <= self.max_distance:
                if min_distance is None or total_errors < min_distance:
                    min_distance = total_errors
        
        return min_distance
    
    def find_matches(self, vocabulary: List[str], 
                     max_results: int = 10) -> List[Tuple[str, int]]:
        """
        Find all vocabulary terms within edit distance, sorted by distance.
        
        Args:
            vocabulary: List of terms to search
            max_results: Maximum results to return
            
        Returns:
            List of (term, distance) tuples, sorted by distance then alphabetically
        """
        matches = []
        
        for term in vocabulary:
            distance = self.get_distance(term)
            if distance is not None:
                matches.append((term, distance))
        
        # Sort by distance, then alphabetically
        matches.sort(key=lambda x: (x[1], x[0]))
        
        return matches[:max_results]


class LevenshteinMatcher:
    """
    Efficient fuzzy matcher using Levenshtein automaton over a vocabulary.
    
    Pre-processes vocabulary into a trie structure for efficient traversal
    with early termination when no matches are possible.
    
    Example:
        >>> vocab = ["test", "testing", "tests", "best", "rest", "hello"]
        >>> matcher = LevenshteinMatcher(vocab)
        >>> matcher.find_similar("tset", max_distance=1)
        [('test', 1)]
        >>> matcher.find_similar("test", max_distance=2)
        [('test', 0), ('best', 1), ('rest', 1), ('tests', 1)]
    """
    
    def __init__(self, vocabulary: List[str]):
        """
        Initialize matcher with vocabulary.
        
        Args:
            vocabulary: List of terms to match against
        """
        self.vocabulary = [w.lower() for w in vocabulary]
        self._trie = self._build_trie(self.vocabulary)
        self._word_freqs: Dict[str, int] = {}
    
    def set_frequencies(self, freqs: Dict[str, int]):
        """Set word frequencies for ranking."""
        self._word_freqs = {k.lower(): v for k, v in freqs.items()}
    
    def _build_trie(self, words: List[str]) -> Dict:
        """Build a trie from vocabulary for efficient traversal."""
        trie = {}
        for word in words:
            node = trie
            for char in word:
                if char not in node:
                    node[char] = {}
                node = node[char]
            node['$'] = word  # Mark end of word, store original
        return trie
    
    def find_similar(self, query: str, max_distance: int = 1, 
                     max_results: int = 10) -> List[Tuple[str, int]]:
        """
        Find vocabulary terms within edit distance of query.
        
        Uses trie traversal with automaton for early termination.
        
        Args:
            query: Query string
            max_distance: Maximum edit distance
            max_results: Maximum results to return
            
        Returns:
            List of (term, distance) tuples, sorted by distance
        """
        query = query.lower()
        automaton = LevenshteinAutomaton(query, max_distance)
        matches = []
        
        def traverse(node: Dict, states: frozenset):
            """Recursively traverse trie with automaton states."""
            # Check if we've found a complete word
            if '$' in node:
                word = node['$']
                if automaton._is_accepting(states):
                    # Calculate actual distance
                    distance = self._min_accepting_distance(states, len(query))
                    if distance is not None:
                        matches.append((word, distance))
            
            # Early termination: no possible matches from this branch
            if not automaton._can_match(states):
                return
            
            # Explore children
            for char, child in node.items():
                if char == '$':
                    continue
                next_states = automaton._step(states, char)
                if automaton._can_match(next_states):
                    traverse(child, next_states)
        
        traverse(self._trie, automaton._initial_states)
        
        # Sort by distance, then by frequency (higher first), then alphabetically
        def sort_key(item):
            term, dist = item
            freq = self._word_freqs.get(term, 0)
            return (dist, -freq, term)
        
        matches.sort(key=sort_key)
        return matches[:max_results]
    
    def _min_accepting_distance(self, states: frozenset, pattern_len: int) -> Optional[int]:
        """Find minimum distance among accepting states."""
        min_dist = None
        for state in states:
            remaining = pattern_len - state.position
            total = state.errors + remaining
            if min_dist is None or total < min_dist:
                min_dist = total
        return min_dist
    
    def find_best_match(self, query: str, max_distance: int = 2) -> Optional[str]:
        """
        Find the best matching term for a query.
        
        Args:
            query: Query string
            max_distance: Maximum edit distance to consider
            
        Returns:
            Best matching term, or None if no match within distance
        """
        matches = self.find_similar(query, max_distance, max_results=1)
        return matches[0][0] if matches else None


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Compute classic Levenshtein distance between two strings.
    
    Uses Wagner-Fischer algorithm with O(min(m,n)) space.
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        Minimum number of edits (insert, delete, substitute) to transform s1 to s2
    """
    s1, s2 = s1.lower(), s2.lower()
    
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    
    if len(s2) == 0:
        return len(s1)
    
    prev_row = list(range(len(s2) + 1))
    
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,      # Insert
                prev_row[j + 1] + 1,  # Delete
                prev_row[j] + cost    # Substitute
            ))
        prev_row = curr_row
    
    return prev_row[-1]


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Compute Damerau-Levenshtein distance (includes transpositions).
    
    Args:
        s1: First string
        s2: Second string
        
    Returns:
        Minimum number of edits including transpositions
    """
    s1, s2 = s1.lower(), s2.lower()
    len1, len2 = len(s1), len(s2)
    
    # Create distance matrix
    d = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    
    for i in range(len1 + 1):
        d[i][0] = i
    for j in range(len2 + 1):
        d[0][j] = j
    
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            d[i][j] = min(
                d[i-1][j] + 1,      # Deletion
                d[i][j-1] + 1,      # Insertion
                d[i-1][j-1] + cost  # Substitution
            )
            # Transposition
            if i > 1 and j > 1 and s1[i-1] == s2[j-2] and s1[i-2] == s2[j-1]:
                d[i][j] = min(d[i][j], d[i-2][j-2] + cost)
    
    return d[len1][len2]
