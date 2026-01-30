"""
Search interface for querying the BM25 index.
"""

import json
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

from .indexer import BM25Index
from .utils import (
    tokenize, Colors, colorize, highlight_match, style_title, style_url,
    style_score, style_number, style_snippet, style_info, style_success
)
from .spellcheck import SpellChecker
from .autocomplete import Autocomplete
from .facets import FacetIndex
from .synonyms import SynonymExpander


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


def check_phrase_match(text: str, phrase_words: List[str]) -> bool:
    """
    Check if a phrase appears in text (words must be adjacent).
    
    Args:
        text: Text to search in
        phrase_words: List of words that must appear in order
        
    Returns:
        True if phrase is found
    """
    if not phrase_words:
        return True
    
    # Tokenize the text
    text_tokens = tokenize(text)
    
    if len(phrase_words) > len(text_tokens):
        return False
    
    # Sliding window search
    for i in range(len(text_tokens) - len(phrase_words) + 1):
        match = True
        for j, word in enumerate(phrase_words):
            if text_tokens[i + j] != word:
                match = False
                break
        if match:
            return True
    
    return False


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


def highlight_terms(text: str, terms: Set[str], marker: str = '**') -> str:
    """
    Highlight search terms in text using markers.
    
    Args:
        text: Text to highlight
        terms: Set of terms to highlight (lowercase)
        marker: Marker to wrap terms with (e.g., '**' or 'CAPS')
        
    Returns:
        Text with highlighted terms
    """
    if not terms or not text:
        return text
    
    # Build pattern for all terms
    term_pattern = r'\b(' + '|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r')\b'
    
    def replacer(match):
        word = match.group(0)
        if word.lower() in terms:
            return f"{marker}{word}{marker}"
        return word
    
    return re.sub(term_pattern, replacer, text, flags=re.IGNORECASE)


def highlight_terms_ansi(text: str, terms: Set[str]) -> str:
    """
    Highlight search terms in text using ANSI color codes.
    
    Args:
        text: Text to highlight
        terms: Set of terms to highlight (lowercase)
        
    Returns:
        Text with ANSI-highlighted terms
    """
    if not terms or not text:
        return text
    
    # Build pattern for all terms
    term_pattern = r'\b(' + '|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r')\b'
    
    def replacer(match):
        word = match.group(0)
        if word.lower() in terms:
            return highlight_match(word)
        return word
    
    return re.sub(term_pattern, replacer, text, flags=re.IGNORECASE)


def find_best_snippet(text: str, terms: Set[str], phrases: List[List[str]], 
                       snippet_length: int = 150) -> str:
    """
    Find the most relevant snippet from text.
    
    Strategy:
        1. Find section with highest query term density
        2. Prefer sections containing phrase matches
        3. Return ~snippet_length chars of context
    
    Args:
        text: Full document text
        terms: Set of search terms (lowercase)
        phrases: List of phrase word lists
        snippet_length: Target snippet length in chars
        
    Returns:
        Most relevant snippet from text
    """
    if not text:
        return ""
    
    text = text.strip()
    
    # If text is short enough, return it all
    if len(text) <= snippet_length:
        return text
    
    # Tokenize text with positions
    word_pattern = re.compile(r'\b[a-zA-Z][a-zA-Z0-9_]*\b')
    matches = list(word_pattern.finditer(text))
    
    if not matches:
        return text[:snippet_length] + '...'
    
    # Score each position by term density in surrounding window
    window_words = 20  # Number of words to consider
    best_score = -1
    best_start = 0
    
    all_query_terms = set(terms)
    for phrase in phrases:
        all_query_terms.update(phrase)
    
    for i in range(len(matches)):
        # Calculate score for window starting at this word
        window_end = min(i + window_words, len(matches))
        window_matches = matches[i:window_end]
        
        score = 0
        found_terms = set()
        
        for m in window_matches:
            word_lower = m.group(0).lower()
            if word_lower in all_query_terms:
                score += 1
                found_terms.add(word_lower)
        
        # Bonus for having multiple different terms
        score += len(found_terms) * 2
        
        # Check for phrase matches in this window
        if phrases:
            window_start_char = matches[i].start()
            window_end_char = window_matches[-1].end() if window_matches else window_start_char + snippet_length
            window_text = text[window_start_char:window_end_char + 50]
            
            for phrase in phrases:
                if check_phrase_match(window_text, phrase):
                    score += 5  # Big bonus for phrase match
        
        if score > best_score:
            best_score = score
            best_start = i
    
    # Extract snippet around best position
    start_match = matches[best_start]
    start_char = max(0, start_match.start() - 20)
    
    # Find end position
    end_word_idx = min(best_start + window_words, len(matches) - 1)
    end_char = min(len(text), matches[end_word_idx].end() + 20)
    
    # Adjust to word boundaries
    if start_char > 0:
        # Find previous space
        space_pos = text.rfind(' ', 0, start_char)
        if space_pos > start_char - 30:
            start_char = space_pos + 1
    
    if end_char < len(text):
        # Find next space
        space_pos = text.find(' ', end_char)
        if space_pos != -1 and space_pos < end_char + 30:
            end_char = space_pos
    
    snippet = text[start_char:end_char]
    
    # Add ellipsis if truncated
    if start_char > 0:
        snippet = '...' + snippet
    if end_char < len(text):
        snippet = snippet + '...'
    
    return snippet


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
        doc_id = self.index.url_to_id.get(url)
        if doc_id is not None:
            return self.index.documents.get(doc_id)
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search engine statistics."""
        return self.index.get_stats()


def format_results(
    results: List[Dict[str, Any]], 
    show_scores: bool = False,
    query_terms: Optional[Set[str]] = None,
    elapsed_ms: Optional[float] = None,
    colorize_output: bool = True
) -> str:
    """
    Format search results for display with beautiful ANSI colors.
    
    Args:
        results: List of result dictionaries
        show_scores: Include BM25 scores in output
        query_terms: Set of query terms for ANSI highlighting (optional)
        elapsed_ms: Search time in milliseconds (optional)
        colorize_output: Use ANSI colors (default: True)
        
    Returns:
        Formatted string
    """
    if not results:
        if colorize_output:
            return style_info("No results found.")
        return "No results found."
    
    lines = []
    
    # Performance header
    if elapsed_ms is not None:
        perf_line = f"Found {len(results)} results in {elapsed_ms:.1f}ms"
        if colorize_output:
            lines.append(style_success(f"✓ {perf_line}"))
        else:
            lines.append(perf_line)
        lines.append("")
    
    for i, result in enumerate(results, 1):
        title = result.get('title', 'Untitled') or 'Untitled'
        url = result['url']
        # Prefer snippet (with highlighting) over description
        snippet = result.get('snippet', '') or result.get('description', '')
        score = result.get('score', 0)
        
        # Truncate title if too long
        if len(title) > 80:
            title = title[:77] + '...'
        
        # Truncate snippet
        if len(snippet) > 200:
            snippet = snippet[:197] + '...'
        
        # Apply ANSI highlighting to snippet if we have query terms
        if colorize_output and query_terms and snippet:
            # Convert **term** markers to ANSI codes
            snippet = re.sub(
                r'\*\*([^*]+)\*\*',
                lambda m: highlight_match(m.group(1)),
                snippet
            )
        
        # Build the result lines with colors
        if colorize_output:
            if show_scores:
                lines.append(f"{style_number(i)} {style_score(score)} {style_title(title)}")
            else:
                lines.append(f"{style_number(i)} {style_title(title)}")
            
            lines.append(f"   {style_url(url)}")
            
            if snippet:
                lines.append(f"   {snippet}")
        else:
            # Plain text output
            if show_scores:
                lines.append(f"{i}. [{score:.4f}] {title}")
            else:
                lines.append(f"{i}. {title}")
            
            lines.append(f"   {url}")
            
            if snippet:
                lines.append(f"   {snippet}")
        
        lines.append("")
    
    return "\n".join(lines)


class EnhancedSearchEngine(SearchEngine):
    """
    Enhanced search engine with additional features:
    - "Did you mean..." spell correction suggestions
    - Autocomplete / type-ahead suggestions
    - Faceted search (filter by section/type)
    - Query expansion with synonyms (disabled by default)
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
                doc_id = self.index.url_to_id.get(r['url'])
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
    ) -> Dict[str, Any]:
        """
        Enhanced search with additional features.
        
        Args:
            query: Search query
            top_k: Maximum results
            min_score: Minimum score threshold
            highlight: Highlight query terms
            snippet_length: Target snippet length
            facet_filters: Optional facet filters (type -> value)
            expand_synonyms: Whether to expand query with synonyms
            
        Returns:
            Dict with 'results', 'suggestion', 'facets' keys
        """
        response: Dict[str, Any] = {
            'results': [],
            'suggestion': None,
            'facets': {},
            'query': query,
            'expanded_query': None
        }
        
        # Parse query
        terms, phrases = parse_query(query)
        
        if not terms and not phrases:
            return response
        
        # Check for spelling suggestions
        if self._spellchecker:
            suggestion = self.get_spelling_suggestion(query)
            if suggestion and suggestion.lower() != query.lower():
                response['suggestion'] = suggestion
        
        # Expand query with synonyms
        expanded_terms = list(terms)
        if expand_synonyms and self._synonyms and terms:
            expanded_terms = self._synonyms.expand_terms(terms, max_per_term=2)
            if expanded_terms != list(terms):
                response['expanded_query'] = ' '.join(expanded_terms)
        
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
            all_doc_ids = {self.index.url_to_id[r['url']] for r in bm25_results 
                          if r['url'] in self.index.url_to_id}
            filtered_doc_ids = self._facets.filter_by_facets(all_doc_ids, facet_filters)
            
            # Map back to URLs
            id_to_url = {v: k for k, v in self.index.url_to_id.items()}
            filtered_urls = {id_to_url[doc_id] for doc_id in filtered_doc_ids}
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
                doc_id = self.index.url_to_id.get(r['url'])
                if doc_id is not None:
                    result['facets'] = self._facets.get_doc_facets(doc_id)
            
            results.append(result)
            
            if len(results) >= top_k:
                break
        
        response['results'] = results
        
        # Get facet counts for results
        if self._facets and results:
            response['facets'] = self.get_facet_counts(results)
        
        return response
    
    def search_simple(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """
        Simple search that returns just results (like base SearchEngine).
        
        For backward compatibility.
        """
        response = self.search(query, top_k=top_k, **kwargs)
        return response['results']
    
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
