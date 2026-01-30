"""
Autocomplete / type-ahead suggestions using a trie data structure.

Provides fast prefix-based term suggestions with optional frequency ranking.
"""

from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict


class TrieNode:
    """A node in the trie structure."""
    
    __slots__ = ['children', 'is_end', 'word', 'frequency']
    
    def __init__(self):
        self.children: Dict[str, 'TrieNode'] = {}
        self.is_end: bool = False
        self.word: Optional[str] = None
        self.frequency: int = 0


class Autocomplete:
    """
    Autocomplete engine using a trie for fast prefix matching.
    
    Supports frequency-based ranking of suggestions.
    """
    
    def __init__(self):
        """Initialize empty autocomplete trie."""
        self.root = TrieNode()
        self._word_count = 0
    
    def add_word(self, word: str, frequency: int = 1):
        """
        Add a word to the autocomplete index.
        
        Args:
            word: Word to add
            frequency: Frequency/weight for ranking (higher = more relevant)
        """
        if not word:
            return
        
        word = word.lower()
        node = self.root
        
        for char in word:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
        
        if not node.is_end:
            self._word_count += 1
        
        node.is_end = True
        node.word = word
        node.frequency += frequency
    
    def add_words(self, words: List[str], frequencies: Optional[Dict[str, int]] = None):
        """
        Add multiple words to the autocomplete index.
        
        Args:
            words: List of words to add
            frequencies: Optional dict mapping words to frequencies
        """
        frequencies = frequencies or {}
        for word in words:
            freq = frequencies.get(word, 1)
            self.add_word(word, freq)
    
    def build_from_index(self, index_terms: Dict[str, int]):
        """
        Build autocomplete from an index of term -> document frequency.
        
        Args:
            index_terms: Dictionary mapping terms to their document frequencies
        """
        for term, doc_freq in index_terms.items():
            self.add_word(term, doc_freq)
    
    def _find_node(self, prefix: str) -> Optional[TrieNode]:
        """Find the node corresponding to a prefix."""
        prefix = prefix.lower()
        node = self.root
        
        for char in prefix:
            if char not in node.children:
                return None
            node = node.children[char]
        
        return node
    
    def _collect_words(self, node: TrieNode, max_results: int) -> List[Tuple[str, int]]:
        """
        Collect all words under a node using DFS.
        
        Args:
            node: Starting node
            max_results: Maximum number of results
            
        Returns:
            List of (word, frequency) tuples
        """
        results = []
        stack = [node]
        
        while stack and len(results) < max_results * 3:  # Collect extra for sorting
            current = stack.pop()
            
            if current.is_end and current.word:
                results.append((current.word, current.frequency))
            
            # Add children to stack (alphabetically for consistent ordering)
            for char in sorted(current.children.keys(), reverse=True):
                stack.append(current.children[char])
        
        return results
    
    def suggest(self, prefix: str, max_suggestions: int = 10) -> List[str]:
        """
        Get autocomplete suggestions for a prefix.
        
        Args:
            prefix: The prefix to complete
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested words, sorted by frequency (descending)
        """
        if not prefix:
            return []
        
        node = self._find_node(prefix)
        if not node:
            return []
        
        # Collect all words with this prefix
        words_with_freq = self._collect_words(node, max_suggestions)
        
        # Sort by frequency (descending), then alphabetically
        words_with_freq.sort(key=lambda x: (-x[1], x[0]))
        
        return [word for word, _ in words_with_freq[:max_suggestions]]
    
    def suggest_with_scores(self, prefix: str, max_suggestions: int = 10) -> List[Tuple[str, int]]:
        """
        Get autocomplete suggestions with their frequencies.
        
        Args:
            prefix: The prefix to complete
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of (word, frequency) tuples, sorted by frequency
        """
        if not prefix:
            return []
        
        node = self._find_node(prefix)
        if not node:
            return []
        
        words_with_freq = self._collect_words(node, max_suggestions)
        words_with_freq.sort(key=lambda x: (-x[1], x[0]))
        
        return words_with_freq[:max_suggestions]
    
    def has_prefix(self, prefix: str) -> bool:
        """Check if any word starts with the given prefix."""
        return self._find_node(prefix) is not None
    
    def contains(self, word: str) -> bool:
        """Check if exact word exists in the index."""
        node = self._find_node(word)
        return node is not None and node.is_end
    
    def get_word_count(self) -> int:
        """Return the number of unique words in the index."""
        return self._word_count
    
    def get_frequency(self, word: str) -> int:
        """Get the frequency of a word, or 0 if not found."""
        node = self._find_node(word)
        if node and node.is_end:
            return node.frequency
        return 0


class MultiWordAutocomplete:
    """
    Autocomplete that handles multi-word queries.
    
    Only completes the last word in a query, preserving previous words.
    """
    
    def __init__(self, autocomplete: Autocomplete):
        """
        Initialize with an Autocomplete instance.
        
        Args:
            autocomplete: The underlying single-word autocomplete
        """
        self.autocomplete = autocomplete
    
    def suggest(self, query: str, max_suggestions: int = 10) -> List[str]:
        """
        Get suggestions for a multi-word query.
        
        Completes only the last word, preserving previous words.
        
        Args:
            query: The query string (may contain multiple words)
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of complete query suggestions
        """
        if not query:
            return []
        
        # Split into previous words and current word being typed
        parts = query.rsplit(' ', 1)
        
        if len(parts) == 1:
            # Single word, just autocomplete it
            prefix = parts[0]
            previous = ''
        else:
            previous, prefix = parts
            previous = previous + ' '
        
        if not prefix:
            return []
        
        # Get suggestions for the current word
        word_suggestions = self.autocomplete.suggest(prefix, max_suggestions)
        
        # Combine with previous words
        return [previous + word for word in word_suggestions]
