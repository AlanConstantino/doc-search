"""
SymSpell fuzzy matching implementation.

Symmetric Delete Spelling Correction algorithm for fast fuzzy search.
Uses deletion-based indexing for O(1) average lookup time.

Reference: https://github.com/wolfgarbe/SymSpell
"""

from typing import Dict, List, Set, Tuple, Optional, Iterator
import json
import gzip

from .spellcheck import damerau_levenshtein_distance


class SymSpell:
    """
    SymSpell fuzzy matching index.
    
    Pre-computes deletions of vocabulary words to enable fast fuzzy lookups.
    For a word of length L and max edit distance D, generates O(L^D) deletions.
    
    Example:
        >>> ss = SymSpell(max_distance=2)
        >>> ss.add_word("python", frequency=1000)
        >>> ss.add_word("pytorch", frequency=500)
        >>> ss.lookup("pyhton")  # typo
        [('python', 1, 1000), ('pytorch', 2, 500)]
    """
    
    def __init__(self, max_distance: int = 2, prefix_length: int = 7):
        """
        Initialize SymSpell index.
        
        Args:
            max_distance: Maximum edit distance for fuzzy matching (1 or 2 recommended)
            prefix_length: Only index this many characters of long words (optimization)
        """
        self.max_distance = max_distance
        self.prefix_length = prefix_length
        
        # deletion → list of (original_word, frequency)
        self.deletes: Dict[str, List[Tuple[str, int]]] = {}
        
        # word → frequency (for exact matches and frequency lookup)
        self.words: Dict[str, int] = {}
        
        # Stats
        self._delete_count = 0
    
    def add_word(self, word: str, frequency: int = 1) -> None:
        """
        Add a word to the index with optional frequency.
        
        Args:
            word: Word to add
            frequency: Word frequency (higher = more likely suggestion)
        """
        word = word.lower()
        
        # Skip very short words
        if len(word) < 2:
            return
        
        # Store word with frequency
        if word in self.words:
            self.words[word] += frequency
        else:
            self.words[word] = frequency
            
            # Generate and store deletions
            for deletion in self._get_deletes(word):
                if deletion not in self.deletes:
                    self.deletes[deletion] = []
                self.deletes[deletion].append((word, frequency))
                self._delete_count += 1
    
    def _get_deletes(self, word: str) -> Set[str]:
        """
        Generate all deletions of a word within max_distance.
        
        For "python" with max_distance=2:
        - Distance 1: ython, pthon, pyhon, pythn, pytho
        - Distance 2: thon, yhon, yton, pthn, ptho, phon, ...
        """
        # Use prefix for long words
        word = word[:self.prefix_length] if len(word) > self.prefix_length else word
        
        deletes = set()
        self._generate_deletes(word, 0, deletes)
        return deletes
    
    def _generate_deletes(self, word: str, depth: int, deletes: Set[str]) -> None:
        """Recursively generate deletions."""
        if depth >= self.max_distance:
            return
        
        for i in range(len(word)):
            deletion = word[:i] + word[i+1:]
            if deletion and deletion not in deletes:
                deletes.add(deletion)
                self._generate_deletes(deletion, depth + 1, deletes)
    
    def lookup(
        self, 
        query: str, 
        max_distance: Optional[int] = None,
        max_results: int = 10
    ) -> List[Tuple[str, int, int]]:
        """
        Find fuzzy matches for a query term.
        
        Args:
            query: Query term (potentially misspelled)
            max_distance: Override max edit distance (default: self.max_distance)
            max_results: Maximum number of results to return
            
        Returns:
            List of (word, edit_distance, frequency) tuples, sorted by
            distance first, then by frequency (descending).
        """
        query = query.lower()
        max_dist = max_distance if max_distance is not None else self.max_distance
        
        candidates: Dict[str, Tuple[int, int]] = {}  # word → (distance, frequency)
        
        # Check exact match
        if query in self.words:
            candidates[query] = (0, self.words[query])
        
        # Use prefix for long queries
        query_prefix = query[:self.prefix_length] if len(query) > self.prefix_length else query
        
        # Check deletions of query
        query_deletes = set([query_prefix])
        self._generate_deletes(query_prefix, 0, query_deletes)
        
        for deletion in query_deletes:
            if deletion in self.deletes:
                for word, freq in self.deletes[deletion]:
                    if word not in candidates:
                        # Calculate actual edit distance
                        dist = damerau_levenshtein_distance(query, word, max_dist)
                        if dist <= max_dist:
                            candidates[word] = (dist, freq)
        
        # Also check if query is a deletion of any word (handles insertions)
        if query in self.deletes:
            for word, freq in self.deletes[query]:
                if word not in candidates:
                    dist = damerau_levenshtein_distance(query, word, max_dist)
                    if dist <= max_dist:
                        candidates[word] = (dist, freq)
        
        # Sort by distance, then by frequency (descending)
        results = [
            (word, dist, freq) 
            for word, (dist, freq) in candidates.items()
        ]
        results.sort(key=lambda x: (x[1], -x[2]))
        
        return results[:max_results]
    
    def lookup_compound(
        self, 
        query: str, 
        max_distance: Optional[int] = None
    ) -> List[Tuple[str, int]]:
        """
        Find fuzzy matches for each word in a multi-word query.
        
        Args:
            query: Multi-word query string
            max_distance: Override max edit distance
            
        Returns:
            List of (original_term, best_match) tuples for terms that have
            fuzzy matches. Terms with exact matches are not included.
        """
        expansions = []
        
        for term in query.lower().split():
            # Skip short terms
            if len(term) < 3:
                continue
            
            # Skip if exact match exists
            if term in self.words:
                continue
            
            matches = self.lookup(term, max_distance=max_distance, max_results=1)
            if matches:
                best_match, distance, _ = matches[0]
                if distance > 0:  # Only include if it's actually a fuzzy match
                    expansions.append((term, best_match))
        
        return expansions
    
    def get_stats(self) -> Dict:
        """Get index statistics."""
        return {
            'word_count': len(self.words),
            'delete_count': self._delete_count,
            'unique_deletes': len(self.deletes),
            'max_distance': self.max_distance,
            'prefix_length': self.prefix_length,
        }
    
    def save(self, path: str, compress: bool = True) -> str:
        """
        Save the SymSpell index to a file.
        
        Args:
            path: Base path (without extension)
            compress: Whether to gzip compress the output
            
        Returns:
            Actual path written (with extension)
        """
        data = {
            'version': 1,
            'max_distance': self.max_distance,
            'prefix_length': self.prefix_length,
            'words': self.words,
            'deletes': {k: v for k, v in self.deletes.items()},
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
    def load(cls, path: str) -> 'SymSpell':
        """
        Load a SymSpell index from a file.
        
        Args:
            path: Path to the index file (.json or .json.gz)
            
        Returns:
            Loaded SymSpell instance
        """
        if path.endswith('.gz'):
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        instance = cls(
            max_distance=data.get('max_distance', 2),
            prefix_length=data.get('prefix_length', 7)
        )
        
        instance.words = data['words']
        instance.deletes = {
            k: [tuple(item) for item in v] 
            for k, v in data['deletes'].items()
        }
        instance._delete_count = sum(len(v) for v in instance.deletes.values())
        
        return instance
