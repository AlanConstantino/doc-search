"""
Synonym expansion for query enhancement.

Expands queries with related terms to improve recall.
Defaults are loaded from data/synonyms.json (editable).
"""

import json
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict


def load_default_synonyms() -> List[Set[str]]:
    """Load default synonym groups from the bundled JSON file."""
    json_path = Path(__file__).parent / 'data' / 'synonyms.json'
    if json_path.exists():
        try:
            with open(json_path, encoding='utf-8') as f:
                data = json.load(f)
            return [set(group) for group in data.get('groups', [])]
        except (json.JSONDecodeError, IOError):
            pass
    # Fallback to empty if file is missing/broken
    return []


def load_synonyms_file(path: str) -> List[Set[str]]:
    """Load synonym groups from a user-provided JSON file.
    
    Args:
        path: Path to JSON file with {"groups": [["term1", "term2"], ...]}
    
    Returns:
        List of synonym group sets
    """
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return [set(group) for group in data.get('groups', [])]


# Built-in programming/technical synonym groups
# Load defaults from JSON file (editable at data/synonyms.json)
DEFAULT_SYNONYM_GROUPS = load_default_synonyms()


class SynonymExpander:
    """
    Expands query terms with synonyms to improve search recall.
    
    Uses synonym groups where all terms in a group are considered equivalent.
    """
    
    def __init__(self, synonym_groups: Optional[List[Set[str]]] = None,
                 include_defaults: bool = True):
        """
        Initialize synonym expander.
        
        Args:
            synonym_groups: Custom synonym groups to add
            include_defaults: Whether to include built-in synonym groups
        """
        # term -> set of synonyms (including the term itself)
        self._synonyms: Dict[str, Set[str]] = defaultdict(set)
        
        if include_defaults:
            for group in DEFAULT_SYNONYM_GROUPS:
                self.add_synonym_group(group)
        
        if synonym_groups:
            for group in synonym_groups:
                self.add_synonym_group(group)
    
    def add_synonym_group(self, terms: Set[str]):
        """
        Add a synonym group.
        
        All terms in the group will be considered synonyms of each other.
        
        Args:
            terms: Set of synonymous terms
        """
        terms_lower = {t.lower() for t in terms if t}
        
        # Merge with existing synonym sets
        # Find all existing synonyms for any term in the group
        all_synonyms = set(terms_lower)
        for term in terms_lower:
            if term in self._synonyms:
                all_synonyms.update(self._synonyms[term])
        
        # Update all terms to point to the merged set
        for term in all_synonyms:
            self._synonyms[term] = all_synonyms
    
    def add_synonym_pair(self, term1: str, term2: str):
        """
        Add a synonym pair.
        
        Args:
            term1: First term
            term2: Second term (synonym of first)
        """
        self.add_synonym_group({term1, term2})
    
    def get_synonyms(self, term: str, include_self: bool = True) -> Set[str]:
        """
        Get synonyms for a term.
        
        Args:
            term: The term to find synonyms for
            include_self: Whether to include the term itself
            
        Returns:
            Set of synonymous terms
        """
        term_lower = term.lower()
        
        if term_lower not in self._synonyms:
            return {term_lower} if include_self else set()
        
        synonyms = self._synonyms[term_lower].copy()
        
        if not include_self:
            synonyms.discard(term_lower)
        
        return synonyms
    
    def expand_terms(self, terms: List[str], max_per_term: int = 3) -> List[str]:
        """
        Expand a list of terms with their synonyms.
        
        Args:
            terms: List of query terms
            max_per_term: Maximum synonyms to add per term
            
        Returns:
            Expanded list of terms (original + synonyms)
        """
        expanded = []
        seen = set()
        
        for term in terms:
            term_lower = term.lower()
            if term_lower not in seen:
                expanded.append(term_lower)
                seen.add(term_lower)
            
            # Add synonyms
            synonyms = self.get_synonyms(term_lower, include_self=False)
            count = 0
            for syn in sorted(synonyms):  # Sort for deterministic order
                if syn not in seen and count < max_per_term:
                    expanded.append(syn)
                    seen.add(syn)
                    count += 1
        
        return expanded
    
    def expand_query(self, query_terms: List[str], 
                     boost_original: float = 2.0) -> List[Tuple[str, float]]:
        """
        Expand query terms with boost weights.
        
        Original terms get higher boost than synonyms.
        
        Args:
            query_terms: List of query terms
            boost_original: Boost factor for original terms
            
        Returns:
            List of (term, boost) tuples
        """
        result = []
        seen = set()
        
        for term in query_terms:
            term_lower = term.lower()
            
            if term_lower not in seen:
                result.append((term_lower, boost_original))
                seen.add(term_lower)
            
            # Add synonyms with lower boost
            for syn in self.get_synonyms(term_lower, include_self=False):
                if syn not in seen:
                    result.append((syn, 1.0))  # Synonyms get base boost
                    seen.add(syn)
        
        return result
    
    def has_synonyms(self, term: str) -> bool:
        """Check if a term has any synonyms."""
        return term.lower() in self._synonyms and len(self._synonyms[term.lower()]) > 1
    
    def get_all_terms(self) -> Set[str]:
        """Get all terms that have synonyms defined."""
        return set(self._synonyms.keys())
    
    def get_synonym_count(self) -> int:
        """Get the number of unique synonym groups."""
        # Count unique groups by finding unique frozensets
        groups = set()
        for synonyms in self._synonyms.values():
            groups.add(frozenset(synonyms))
        return len(groups)
    
    def to_dict(self) -> Dict[str, List[str]]:
        """Serialize to dictionary for storage."""
        # Only store unique groups
        groups = set()
        for synonyms in self._synonyms.values():
            groups.add(frozenset(synonyms))
        
        return {
            'groups': [list(g) for g in groups]
        }
    
    @classmethod
    def from_dict(cls, data: Dict, include_defaults: bool = False) -> 'SynonymExpander':
        """
        Deserialize from dictionary.
        
        Args:
            data: Dictionary with 'groups' key
            include_defaults: Whether to include default synonyms
        """
        groups = [set(g) for g in data.get('groups', [])]
        return cls(synonym_groups=groups, include_defaults=include_defaults)


class QueryExpander:
    """
    High-level query expansion combining multiple strategies.
    
    Combines synonym expansion with optional stemming awareness.
    """
    
    def __init__(self, synonym_expander: Optional[SynonymExpander] = None,
                 use_stemming: bool = False):
        """
        Initialize query expander.
        
        Args:
            synonym_expander: SynonymExpander instance (creates default if None)
            use_stemming: Whether to stem terms before synonym lookup
        """
        self.synonyms = synonym_expander or SynonymExpander()
        self.use_stemming = use_stemming
    
    def expand(self, terms: List[str], include_original: bool = True,
               max_synonyms: int = 2) -> List[str]:
        """
        Expand query terms.
        
        Args:
            terms: Original query terms
            include_original: Include original terms in output
            max_synonyms: Maximum synonyms per term
            
        Returns:
            Expanded list of terms
        """
        result = []
        seen = set()
        
        for term in terms:
            term_lower = term.lower()
            
            # Optionally stem
            lookup_term = term_lower
            if self.use_stemming:
                from .stemmer import stem
                lookup_term = stem(term_lower)
            
            if include_original and term_lower not in seen:
                result.append(term_lower)
                seen.add(term_lower)
            
            # Get synonyms
            synonyms = self.synonyms.get_synonyms(lookup_term, include_self=False)
            count = 0
            for syn in sorted(synonyms):
                if syn not in seen and count < max_synonyms:
                    result.append(syn)
                    seen.add(syn)
                    count += 1
        
        return result
