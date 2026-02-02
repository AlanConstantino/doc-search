"""
Search interface for querying the BM25 index.
"""

import json
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

from .indexer import BM25Index
from .utils import tokenize
from .spellcheck import SpellChecker
from .autocomplete import Autocomplete
from .facets import FacetIndex
from .synonyms import SynonymExpander
from .searcher_utils import (
    highlight_terms, highlight_terms_ansi, find_best_snippet,
    format_results, check_phrase_match
)


def parse_query(query: str) -> Tuple[List[str], List[List[str]]]:
    """
    Parse a query into individual terms and phrase groups.
    
    Supports:
        - Regular terms: python tutorial
        - Exact phrases: "list comprehension"
        - Mixed: python "list comprehension" tutorial
    
    Args:
        query: Search query string
        
    Returns:
        Tuple of (individual_terms, phrase_groups)
        where phrase_groups is a list of word lists
    """
    phrases = []
    
    # Extract quoted phrases
    phrase_pattern = r'"([^"]+)"'
    for match in re.finditer(phrase_pattern, query):
        phrase_text = match.group(1)
        # Tokenize phrase but preserve order
        phrase_words = tokenize(phrase_text)
        if phrase_words:
            phrases.append(phrase_words)
    
    # Remove quoted phrases from query
    remaining = re.sub(phrase_pattern, ' ', query)
    
    # Tokenize remaining terms
    terms = tokenize(remaining)
    
    return terms, phrases


def find_phrase_positions(text: str, phrase_words: List[str]) -> List[int]:
    """
    Find character positions where a phrase starts in text.
    
    Args:
        text: Text to search in  
        phrase_words: List of words that must appear in order
        
    Returns:
        List of starting character positions
    """
    positions = []
    if not phrase_words:
        return positions
    
    text_lower = text.lower()
    
    # Build regex pattern for phrase
    # Match words with possible punctuation/whitespace between
    pattern_parts = []
    for word in phrase_words:
        pattern_parts.append(re.escape(word))
    
    # Words can be separated by whitespace or punctuation
    pattern = r'\b' + r'\W+'.join(pattern_parts) + r'\b'
    
    for match in re.finditer(pattern, text_lower):
        positions.append(match.start())
    
    return positions


class SearchEngine:
    """
    High-level search interface with phrase search and snippet highlighting.
    """
    
    def __init__(self, index: BM25Index, pages_dir: Optional[Path] = None):
        self.index = index
        self.pages_dir = pages_dir
    
    @classmethod
    def load(cls, index_path: Path) -> 'SearchEngine':
        """Load search engine from saved index."""
        index_path = Path(index_path)
        index = BM25Index.load(index_path)
        
        # Try to find pages directory
        pages_dir = None
        parent = index_path.parent
        if (parent / 'pages').is_dir():
            pages_dir = parent / 'pages'
        
        return cls(index, pages_dir)
    
    def _load_page_text(self, url: str) -> Optional[str]:
        """Load full page text from disk."""
        if not self.pages_dir:
            return None
        
        from .utils import url_to_filename
        filename = url_to_filename(url) + '.json'
        filepath = self.pages_dir / filename
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return data.get('text', '')
        except (json.JSONDecodeError, IOError):
            return None
    
    def search(
        self, 
        query: str, 
        top_k: int = 10,
        min_score: float = 0.0,
        highlight: bool = True,
        snippet_length: int = 150
    ) -> List[Dict[str, Any]]:
        """
        Search the index with phrase support and highlighted snippets.
        
        Args:
            query: Search query (supports "phrase search")
            top_k: Maximum number of results
            min_score: Minimum score threshold
            highlight: Highlight query terms in snippets
            snippet_length: Target snippet length
            
        Returns:
            List of result dictionaries
        """
        # Parse query into terms and phrases
        terms, phrases = parse_query(query)
        
        if not terms and not phrases:
            return []
        
        # Flatten phrases into terms for BM25 scoring
        all_terms = list(terms)
        for phrase in phrases:
            all_terms.extend(phrase)
        
        # Get initial results from BM25
        # Request more than needed to filter by phrase
        initial_k = top_k * 3 if phrases else top_k
        bm25_results = self.index.search(' '.join(all_terms), top_k=initial_k)
        
        if min_score > 0:
            bm25_results = [r for r in bm25_results if r['score'] >= min_score]
        
        # If we have phrases, filter results that don't contain them
        results = []
        terms_set = set(terms)
        for phrase in phrases:
            terms_set.update(phrase)
        
        for r in bm25_results:
            # Load full text if we need to check phrases or generate snippets
            page_text = None
            if phrases or (self.pages_dir and snippet_length > 0):
                page_text = self._load_page_text(r['url'])
            
            # Check phrase matches
            if phrases and page_text:
                # Must contain all phrases
                all_phrases_found = True
                for phrase in phrases:
                    if not check_phrase_match(page_text, phrase):
                        # Also check title
                        if not check_phrase_match(r.get('title', ''), phrase):
                            all_phrases_found = False
                            break
                
                if not all_phrases_found:
                    continue
            
            # Generate better snippet
            snippet = r.get('description', '')
            if page_text:
                snippet = find_best_snippet(page_text, terms_set, phrases, snippet_length)
            
            # Highlight terms if requested
            if highlight and snippet:
                snippet = highlight_terms(snippet, terms_set)
            
            result = {
                'url': r['url'],
                'title': r.get('title', ''),
                'snippet': snippet,
                'description': r.get('description', ''),  # Keep original too
                'score': r.get('score', 0)
            }
            
            results.append(result)
            
            if len(results) >= top_k:
                break
        
        return results
    
    def search_with_context(
        self,
        query: str,
        top_k: int = 10,
        context_length: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Search and include text context for each result.
        """
        return self.search(query, top_k=top_k, snippet_length=context_length)
    
    def get_document(self, url: str) -> Optional[Dict[str, Any]]:
        """Get document metadata by URL."""
        doc_id = self.index.get_doc_id(url)
        if doc_id is not None:
            return self.index.get_document(doc_id)
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search engine statistics."""
        return self.index.get_stats()


class EnhancedSearchEngine(SearchEngine):
    """
    Enhanced search engine with additional features:
    - "Did you mean..." spell correction suggestions
    - Autocomplete / type-ahead suggestions
    - Faceted search (filter by section/type)
    - Query expansion with synonyms (disabled by default)
    
    Note: The search() method returns List[Dict[str, Any]] for LSP compliance
    with SearchEngine. Enhanced metadata (suggestion, facets, etc.) is stored
    in instance attributes after each search, or use search_enhanced() for
    a dict response containing all metadata.
    """
    
    def __init__(self, index: BM25Index, pages_dir: Optional[Path] = None,
                 enable_spellcheck: bool = True,
                 enable_autocomplete: bool = True,
                 enable_facets: bool = True,
                 enable_synonyms: bool = False,
                 synonym_groups: Optional[List[Set[str]]] = None):
        """
        Initialize enhanced search engine.
        
        Args:
            index: The BM25 index
            pages_dir: Directory containing page JSON files
            enable_spellcheck: Enable "Did you mean..." suggestions
            enable_autocomplete: Enable type-ahead suggestions
            enable_facets: Enable faceted search
            enable_synonyms: Enable query expansion with synonyms (default: False)
            synonym_groups: Custom synonym groups (if None and enabled, uses defaults)
        """
        super().__init__(index, pages_dir)
        
        self._spellcheck_enabled = enable_spellcheck
        self._autocomplete_enabled = enable_autocomplete
        self._facets_enabled = enable_facets
        self._synonyms_enabled = enable_synonyms
        self._custom_synonym_groups = synonym_groups
        
        # Initialize components
        self._spellchecker: Optional[SpellChecker] = None
        self._autocomplete: Optional[Autocomplete] = None
        self._facets: Optional[FacetIndex] = None
        self._synonyms: Optional[SynonymExpander] = None
        
        # Last search metadata (populated after each search() call)
        self.last_suggestion: Optional[str] = None
        self.last_facets: Dict[str, Dict[str, int]] = {}
        self.last_query: str = ''
        self.last_expanded_query: Optional[str] = None
        
        # Build enhanced features from index
        self._build_enhanced_features()
    
    def _build_enhanced_features(self):
        """Build enhanced features from the index data."""
        # Get all terms from index for spellcheck and autocomplete
        vocabulary = set(self.index.index.keys())
        
        if self._spellcheck_enabled:
            self._spellchecker = SpellChecker(vocabulary, max_distance=2)
        
        if self._autocomplete_enabled:
            self._autocomplete = Autocomplete()
            # Use doc_freqs for term frequencies
            self._autocomplete.build_from_index(dict(self.index.doc_freqs))
        
        if self._facets_enabled:
            self._facets = FacetIndex()
            # Build facets from document metadata
            for doc_id, doc in self.index.documents.items():
                headings = []  # We don't store headings in index, use title
                self._facets.add_document(
                    doc_id=doc_id,
                    url=doc['url'],
                    title=doc.get('title', ''),
                    headings=headings
                )
        
        if self._synonyms_enabled:
            if self._custom_synonym_groups:
                # Use custom synonyms only
                self._synonyms = SynonymExpander(
                    synonym_groups=self._custom_synonym_groups,
                    include_defaults=False
                )
            else:
                # Use built-in programming synonyms
                self._synonyms = SynonymExpander(include_defaults=True)
    
    @classmethod
    def load(cls, index_path: Path, **kwargs) -> 'EnhancedSearchEngine':
        """Load enhanced search engine from saved index."""
        index_path = Path(index_path)
        index = BM25Index.load(index_path)
        
        # Try to find pages directory
        pages_dir = None
        parent = index_path.parent
        if (parent / 'pages').is_dir():
            pages_dir = parent / 'pages'
        
        return cls(index, pages_dir, **kwargs)
    
    def get_spelling_suggestion(self, query: str) -> Optional[str]:
        """
        Get spelling suggestion for a query.
        
        Args:
            query: The search query
            
        Returns:
            Suggested corrected query, or None if no correction needed
        """
        if not self._spellchecker:
            return None
        
        terms, _ = parse_query(query)
        if not terms:
            return None
        
        result = self._spellchecker.suggest_query(terms)
        if result:
            _, suggestion = result
            return suggestion
        
        return None
    
    def get_autocomplete_suggestions(self, prefix: str, 
                                      max_suggestions: int = 10) -> List[str]:
        """
        Get autocomplete suggestions for a prefix.
        
        Args:
            prefix: The partial query
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested completions
        """
        if not self._autocomplete:
            return []
        
        return self._autocomplete.suggest(prefix, max_suggestions)
    
    def get_facet_counts(self, 
                         results: Optional[List[Dict[str, Any]]] = None
                         ) -> Dict[str, Dict[str, int]]:
        """
        Get facet counts for filtering.
        
        Args:
            results: Optional search results to get counts for
                    (if None, returns counts for all documents)
            
        Returns:
            Dict mapping facet_type -> value -> count
        """
        if not self._facets:
            return {}
        
        if results:
            # Get doc IDs from results
            doc_ids = set()
            for r in results:
                doc_id = self.index.get_doc_id(r['url'])
                if doc_id is not None:
                    doc_ids.add(doc_id)
            return self._facets.get_facet_counts(doc_ids)
        else:
            # Return all facet values
            return {
                ftype: self._facets.get_facet_values(ftype)
                for ftype in self._facets.get_all_facet_types()
            }
    
    def search(
        self, 
        query: str, 
        top_k: int = 10,
        min_score: float = 0.0,
        highlight: bool = True,
        snippet_length: int = 150,
        facet_filters: Optional[Dict[str, str]] = None,
        expand_synonyms: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search the index with enhanced features.
        
        Returns the same type as SearchEngine.search() for LSP compliance.
        Enhanced metadata (suggestion, facets, expanded_query) is stored in
        instance attributes: last_suggestion, last_facets, last_expanded_query.
        
        Use search_enhanced() to get a dict response with all metadata included.
        
        Args:
            query: Search query
            top_k: Maximum results
            min_score: Minimum score threshold
            highlight: Highlight query terms
            snippet_length: Target snippet length
            facet_filters: Optional facet filters (type -> value)
            expand_synonyms: Whether to expand query with synonyms
            
        Returns:
            List of result dictionaries (same as SearchEngine.search())
        """
        # Reset last search metadata
        self.last_suggestion = None
        self.last_facets = {}
        self.last_query = query
        self.last_expanded_query = None
        
        # Parse query
        terms, phrases = parse_query(query)
        
        if not terms and not phrases:
            return []
        
        # Check for spelling suggestions
        if self._spellchecker:
            suggestion = self.get_spelling_suggestion(query)
            if suggestion and suggestion.lower() != query.lower():
                self.last_suggestion = suggestion
        
        # Expand query with synonyms
        expanded_terms = list(terms)
        if expand_synonyms and self._synonyms and terms:
            expanded_terms = self._synonyms.expand_terms(terms, max_per_term=2)
            if expanded_terms != list(terms):
                self.last_expanded_query = ' '.join(expanded_terms)
        
        # Flatten phrases into terms for BM25 scoring
        all_terms = list(expanded_terms)
        for phrase in phrases:
            all_terms.extend(phrase)
        
        # Get initial results from BM25
        initial_k = top_k * 3 if phrases or facet_filters else top_k
        bm25_results = self.index.search(' '.join(all_terms), top_k=initial_k)
        
        if min_score > 0:
            bm25_results = [r for r in bm25_results if r['score'] >= min_score]
        
        # Apply facet filters
        if facet_filters and self._facets:
            filtered_urls = set()
            all_doc_ids = set()
            for r in bm25_results:
                doc_id = self.index.get_doc_id(r['url'])
                if doc_id is not None:
                    all_doc_ids.add(doc_id)
            filtered_doc_ids = self._facets.filter_by_facets(all_doc_ids, facet_filters)
            
            # Map back to URLs using document metadata
            for doc_id in filtered_doc_ids:
                doc = self.index.get_document(doc_id)
                if doc:
                    filtered_urls.add(doc['url'])
            bm25_results = [r for r in bm25_results if r['url'] in filtered_urls]
        
        # Process results (phrase matching, snippets, etc.)
        results = []
        terms_set = set(terms)
        for phrase in phrases:
            terms_set.update(phrase)
        
        for r in bm25_results:
            page_text = None
            if phrases or (self.pages_dir and snippet_length > 0):
                page_text = self._load_page_text(r['url'])
            
            # Check phrase matches
            if phrases and page_text:
                all_phrases_found = True
                for phrase in phrases:
                    if not check_phrase_match(page_text, phrase):
                        if not check_phrase_match(r.get('title', ''), phrase):
                            all_phrases_found = False
                            break
                
                if not all_phrases_found:
                    continue
            
            # Generate snippet
            snippet = r.get('description', '')
            if page_text:
                snippet = find_best_snippet(page_text, terms_set, phrases, snippet_length)
            
            if highlight and snippet:
                snippet = highlight_terms(snippet, terms_set)
            
            result = {
                'url': r['url'],
                'title': r.get('title', ''),
                'snippet': snippet,
                'description': r.get('description', ''),
                'score': r.get('score', 0)
            }
            
            # Add facets for this result
            if self._facets:
                doc_id = self.index.get_doc_id(r['url'])
                if doc_id is not None:
                    result['facets'] = self._facets.get_doc_facets(doc_id)
            
            results.append(result)
            
            if len(results) >= top_k:
                break
        
        # Get facet counts for results
        if self._facets and results:
            self.last_facets = self.get_facet_counts(results)
        
        return results
    
    def search_enhanced(
        self, 
        query: str, 
        top_k: int = 10,
        min_score: float = 0.0,
        highlight: bool = True,
        snippet_length: int = 150,
        facet_filters: Optional[Dict[str, str]] = None,
        expand_synonyms: bool = True
    ) -> Dict[str, Any]:
        """
        Enhanced search that returns a dict with results and metadata.
        
        This is a convenience method that calls search() and packages the
        results with the metadata stored in instance attributes.
        
        Args:
            query: Search query
            top_k: Maximum results
            min_score: Minimum score threshold
            highlight: Highlight query terms
            snippet_length: Target snippet length
            facet_filters: Optional facet filters (type -> value)
            expand_synonyms: Whether to expand query with synonyms
            
        Returns:
            Dict with 'results', 'suggestion', 'facets', 'query', 'expanded_query' keys
        """
        results = self.search(
            query=query,
            top_k=top_k,
            min_score=min_score,
            highlight=highlight,
            snippet_length=snippet_length,
            facet_filters=facet_filters,
            expand_synonyms=expand_synonyms
        )
        
        return {
            'results': results,
            'suggestion': self.last_suggestion,
            'facets': self.last_facets,
            'query': self.last_query,
            'expanded_query': self.last_expanded_query
        }
    
    def search_simple(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        Simple search that returns just results (like base SearchEngine).
        
        Deprecated: Use search() directly, which now returns List[Dict[str, Any]].
        This method is kept for backward compatibility.
        """
        return self.search(query, top_k=top_k, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get enhanced search engine statistics."""
        stats = super().get_stats()
        
        stats['features'] = {
            'spellcheck': self._spellcheck_enabled,
            'autocomplete': self._autocomplete_enabled,
            'facets': self._facets_enabled,
            'synonyms': self._synonyms_enabled
        }
        
        if self._autocomplete:
            stats['autocomplete_terms'] = self._autocomplete.get_word_count()
        
        if self._facets:
            stats['facet_stats'] = self._facets.get_stats()
        
        if self._synonyms:
            stats['synonym_groups'] = self._synonyms.get_synonym_count()
        
        return stats
