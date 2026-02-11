"""
Search interface for querying the BM25 index.
"""

import json
import re
import sqlite3
import time
import warnings
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import List, Dict, Any, Optional, Set, Tuple

from .indexer import BM25Index
from .utils import tokenize
from .spellcheck import SpellChecker
from .autocomplete import Autocomplete
from .facets import FacetIndex
from .synonyms import SynonymExpander
from .symspell import SymSpell
from .ngram import NGramIndex
from .searcher_utils import (
    highlight_terms, highlight_terms_ansi, find_best_snippet,
    format_results, check_phrase_match
)


def compute_index_fingerprint(index_path: Path) -> str:
    """
    Compute a fingerprint for the index based on file modification time.
    
    The fingerprint changes whenever the index file is modified (re-indexed).
    Used to invalidate cache when the index changes.
    
    Args:
        index_path: Path to the index file
        
    Returns:
        A string fingerprint based on file mtime
    """
    return str(Path(index_path).stat().st_mtime)


class SearchCache:
    """
    Thread-safe LRU cache for search results with optional TTL and persistence.
    
    Args:
        maxsize: Maximum number of cached queries (default: 128)
        ttl: Time-to-live in seconds. Set to 0 or None to disable TTL
             (entries only evicted when cache is full). Default: None.
        cache_path: Optional path for SQLite persistence. If provided, cache
                    survives restarts. If None, uses in-memory only.
        index_fingerprint: Optional fingerprint of the index. If provided and
                          the stored fingerprint doesn't match, cache is cleared.
    """
    
    def __init__(
        self, 
        maxsize: int = 128, 
        ttl: Optional[float] = None,
        cache_path: Optional[Path] = None,
        index_fingerprint: Optional[str] = None,
        index_path: Optional[Path] = None
    ):
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache_path = Path(cache_path) if cache_path else None
        self.index_fingerprint = index_fingerprint
        self.index_path = Path(index_path) if index_path else None
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        self._db: Optional[sqlite3.Connection] = None
        self._last_fingerprint_check = 0.0
        self._fingerprint_check_interval = 5.0  # Check every 5 seconds
        
        if self.cache_path:
            self._init_db()
            if not self._check_fingerprint():
                self._clear_db()
                self._store_fingerprint()
            self._load_from_db()
    
    def _init_db(self):
        """Initialize SQLite database for persistent cache."""
        self._db = sqlite3.connect(str(self.cache_path), check_same_thread=False)
        self._db.execute('''
            CREATE TABLE IF NOT EXISTS search_cache (
                key TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                result TEXT NOT NULL,
                last_access REAL NOT NULL
            )
        ''')
        self._db.execute('''
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        self._db.execute('CREATE INDEX IF NOT EXISTS idx_last_access ON search_cache(last_access)')
        self._db.commit()
    
    def _check_fingerprint(self) -> bool:
        """Check if stored fingerprint matches current index fingerprint."""
        if not self._db or not self.index_fingerprint:
            return True  # No fingerprint to check
        
        cursor = self._db.execute(
            "SELECT value FROM cache_metadata WHERE key = 'index_fingerprint'"
        )
        row = cursor.fetchone()
        
        if not row:
            return False  # No stored fingerprint, need to initialize
        
        return row[0] == self.index_fingerprint
    
    def _store_fingerprint(self):
        """Store current index fingerprint in database."""
        if not self._db or not self.index_fingerprint:
            return
        
        self._db.execute('''
            INSERT OR REPLACE INTO cache_metadata (key, value)
            VALUES ('index_fingerprint', ?)
        ''', (self.index_fingerprint,))
        self._db.commit()
    
    def _clear_db(self):
        """Clear all entries from the database."""
        if not self._db:
            return
        self._db.execute('DELETE FROM search_cache')
        self._db.commit()
    
    def _check_index_changed(self) -> bool:
        """
        Check if the index has been modified since last check.
        
        Called periodically to detect re-indexing while server is running.
        Returns True if cache was invalidated, False otherwise.
        """
        if not self.index_path:
            return False
        
        now = time.time()
        # Only check every few seconds to avoid stat() on every request
        if now - self._last_fingerprint_check < self._fingerprint_check_interval:
            return False
        
        self._last_fingerprint_check = now
        
        try:
            current_fingerprint = compute_index_fingerprint(self.index_path)
        except (FileNotFoundError, OSError):
            return False
        
        if current_fingerprint != self.index_fingerprint:
            # Index was rebuilt - clear cache
            with self._lock:
                self._cache.clear()
                if self._db:
                    self._clear_db()
                    self.index_fingerprint = current_fingerprint
                    self._store_fingerprint()
                else:
                    self.index_fingerprint = current_fingerprint
            return True
        
        return False
    
    def _load_from_db(self):
        """Load valid cache entries from database on startup."""
        if not self._db:
            return
        
        now = time.time()
        cursor = self._db.execute(
            'SELECT key, timestamp, result FROM search_cache ORDER BY last_access ASC'
        )
        
        expired_keys = []
        for key, timestamp, result_json in cursor:
            # Check TTL
            if self.ttl and (now - timestamp) > self.ttl:
                expired_keys.append(key)
                continue
            
            # Only load up to maxsize
            if len(self._cache) >= self.maxsize:
                break
            
            try:
                result = json.loads(result_json)
                self._cache[key] = (timestamp, result)
            except json.JSONDecodeError:
                expired_keys.append(key)
        
        # Clean up expired entries
        if expired_keys:
            self._db.executemany(
                'DELETE FROM search_cache WHERE key = ?',
                [(k,) for k in expired_keys]
            )
            self._db.commit()
    
    def _make_key(self, query: str, **kwargs) -> str:
        """Create a cache key from query and parameters."""
        # Sort kwargs for consistent key generation
        sorted_kwargs = sorted(kwargs.items())
        return f"{query}|{sorted_kwargs}"
    
    def get(self, query: str, **kwargs) -> Optional[Any]:
        """
        Get cached result if it exists and hasn't expired.
        
        Returns None if not found or expired.
        Also checks if the index has changed and clears cache if so.
        """
        # Check if index was rebuilt (clears cache if so)
        self._check_index_changed()
        
        key = self._make_key(query, **kwargs)
        
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            timestamp, result = self._cache[key]
            
            # Check TTL
            if self.ttl and (time.time() - timestamp) > self.ttl:
                del self._cache[key]
                if self._db:
                    self._db.execute('DELETE FROM search_cache WHERE key = ?', (key,))
                    self._db.commit()
                self._misses += 1
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            
            # Update last_access in DB
            if self._db:
                self._db.execute(
                    'UPDATE search_cache SET last_access = ? WHERE key = ?',
                    (time.time(), key)
                )
                self._db.commit()
            
            self._hits += 1
            return result
    
    def set(self, query: str, result: Any, **kwargs):
        """Cache a search result."""
        key = self._make_key(query, **kwargs)
        now = time.time()
        
        with self._lock:
            # Remove oldest if at capacity
            while len(self._cache) >= self.maxsize:
                oldest_key, _ = self._cache.popitem(last=False)
                if self._db:
                    self._db.execute('DELETE FROM search_cache WHERE key = ?', (oldest_key,))
            
            self._cache[key] = (now, result)
            
            # Persist to DB
            if self._db:
                result_json = json.dumps(result)
                self._db.execute('''
                    INSERT OR REPLACE INTO search_cache (key, timestamp, result, last_access)
                    VALUES (?, ?, ?, ?)
                ''', (key, now, result_json, now))
                self._db.commit()
    
    def clear(self):
        """Clear all cached results."""
        with self._lock:
            self._cache.clear()
            if self._db:
                self._db.execute('DELETE FROM search_cache')
                self._db.commit()
    
    def close(self):
        """Close database connection."""
        if self._db:
            self._db.close()
            self._db = None
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                'size': len(self._cache),
                'maxsize': self.maxsize,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f"{hit_rate:.1f}%",
                'ttl': self.ttl,
                'persistent': self.cache_path is not None,
                'cache_path': str(self.cache_path) if self.cache_path else None
            }


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
    
    def __init__(
        self, 
        index: BM25Index, 
        pages_dir: Optional[Path] = None,
        cache_size: int = 0,
        cache_ttl: Optional[float] = None,
        cache_path: Optional[Path] = None,
        index_path: Optional[Path] = None
    ):
        """
        Initialize the search engine.
        
        Args:
            index: The BM25 index to search
            pages_dir: Optional directory containing page JSON files
            cache_size: Max number of queries to cache (0 to disable caching)
            cache_ttl: Cache TTL in seconds (None = never expire)
            cache_path: Optional path for persistent cache (survives restarts)
            index_path: Optional path to index file (for cache invalidation)
        """
        self.index = index
        self.pages_dir = pages_dir
        
        # Compute index fingerprint for cache invalidation (needs index_path)
        fingerprint = None
        if cache_path and index_path:
            fingerprint = compute_index_fingerprint(index_path)
        
        self._cache = SearchCache(
            maxsize=cache_size, 
            ttl=cache_ttl,
            cache_path=cache_path,
            index_fingerprint=fingerprint,
            index_path=index_path  # For runtime cache invalidation on re-index
        ) if cache_size > 0 else None
    
    @classmethod
    def load(
        cls, 
        index_path: Path,
        cache_size: int = 0,
        cache_ttl: Optional[float] = None,
        cache_path: Optional[Path] = None
    ) -> 'SearchEngine':
        """
        Load search engine from saved index.
        
        Args:
            index_path: Path to the saved index file
            cache_size: Max number of queries to cache (0 to disable)
            cache_ttl: Cache TTL in seconds (None = never expire)
            cache_path: Optional path for persistent cache (survives restarts)
        """
        index_path = Path(index_path)
        index = BM25Index.load(index_path)
        
        # Try to find pages directory
        pages_dir = None
        parent = index_path.parent
        if (parent / 'pages').is_dir():
            pages_dir = parent / 'pages'
        
        return cls(index, pages_dir, cache_size=cache_size, cache_ttl=cache_ttl, 
                   cache_path=cache_path, index_path=index_path)
    
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
        # Check cache first
        if self._cache:
            cached = self._cache.get(
                query, top_k=top_k, min_score=min_score, 
                highlight=highlight, snippet_length=snippet_length
            )
            if cached is not None:
                return cached
        
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
        
        # Cache the results
        if self._cache:
            self._cache.set(
                query, results, top_k=top_k, min_score=min_score,
                highlight=highlight, snippet_length=snippet_length
            )
        
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
    
    def get_cache_stats(self) -> Optional[Dict[str, Any]]:
        """Get cache statistics, or None if caching is disabled."""
        if self._cache:
            return self._cache.stats()
        return None
    
    def clear_cache(self):
        """Clear the search result cache."""
        if self._cache:
            self._cache.clear()
    
    @property
    def cache_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._cache is not None


class EnhancedSearchEngine(SearchEngine):
    """
    Enhanced search engine with additional features:
    - "Did you mean..." spell correction suggestions
    - Autocomplete / type-ahead suggestions
    - Faceted search (filter by section/type)
    - Query expansion with synonyms (disabled by default)
    - Fuzzy search with SymSpell (enabled by default if index exists)
    
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
                 enable_symspell: bool = True,
                 enable_ngram: bool = True,
                 synonym_groups: Optional[List[Set[str]]] = None,
                 symspell_index: Optional[SymSpell] = None,
                 ngram_index: Optional[NGramIndex] = None,
                 cache_size: int = 0,
                 cache_ttl: Optional[float] = None,
                 cache_path: Optional[Path] = None,
                 index_path: Optional[Path] = None):
        """
        Initialize enhanced search engine.
        
        Args:
            index: The BM25 index
            pages_dir: Directory containing page JSON files
            enable_spellcheck: Enable "Did you mean..." suggestions
            enable_autocomplete: Enable type-ahead suggestions
            enable_facets: Enable faceted search
            enable_synonyms: Enable query expansion with synonyms (default: False)
            enable_symspell: Enable SymSpell for suggestions (default: True)
            enable_ngram: Enable n-gram index for prefix/substring search (default: True)
            synonym_groups: Custom synonym groups (if None and enabled, uses defaults)
            symspell_index: Pre-loaded SymSpell index (if None, will try to load from disk)
            ngram_index: Pre-loaded NGram index (if None, will try to load from disk)
            cache_size: Max number of queries to cache (0 to disable)
            cache_ttl: Cache TTL in seconds (None = never expire)
            cache_path: Optional path for persistent cache (survives restarts)
            index_path: Optional path to index file (for cache invalidation)
        """
        super().__init__(index, pages_dir, cache_size=cache_size, cache_ttl=cache_ttl, 
                         cache_path=cache_path, index_path=index_path)
        
        self._spellcheck_enabled = enable_spellcheck
        self._autocomplete_enabled = enable_autocomplete
        self._facets_enabled = enable_facets
        self._synonyms_enabled = enable_synonyms
        self._symspell_enabled = enable_symspell
        self._ngram_enabled = enable_ngram
        self._custom_synonym_groups = synonym_groups
        self._index_path = index_path
        
        # Initialize components
        self._spellchecker: Optional[SpellChecker] = None
        self._autocomplete: Optional[Autocomplete] = None
        self._facets: Optional[FacetIndex] = None
        self._synonyms: Optional[SynonymExpander] = None
        self._symspell: Optional[SymSpell] = symspell_index
        self._ngram: Optional[NGramIndex] = ngram_index
        
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
                    headings=headings,
                    doc_type=doc.get('doc_type', 'html')
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
        
        if self._symspell_enabled and self._symspell is None:
            # Try to load SymSpell index from disk
            self._symspell = self._load_symspell_index()
        
        if self._ngram_enabled and self._ngram is None:
            # Try to load n-gram index from disk
            self._ngram = self._load_ngram_index()
    
    def _load_ngram_index(self) -> Optional[NGramIndex]:
        """Try to load n-gram index from disk."""
        if not self._index_path:
            return None
        
        parent = Path(self._index_path).parent
        
        # Check for compressed and uncompressed versions
        for candidate in [parent / 'ngram.json.gz', parent / 'ngram.json']:
            if candidate.exists():
                try:
                    return NGramIndex.load(str(candidate))
                except Exception:
                    return None
        
        return None
    
    def _load_symspell_index(self) -> Optional[SymSpell]:
        """Try to load SymSpell index from disk."""
        if not self._index_path:
            return None
        
        parent = Path(self._index_path).parent
        
        # Check for compressed and uncompressed versions
        for candidate in [parent / 'fuzzy.json.gz', parent / 'fuzzy.json']:
            if candidate.exists():
                try:
                    return SymSpell.load(str(candidate))
                except Exception:
                    return None
        
        return None
    
    @property
    def symspell_enabled(self) -> bool:
        """Check if SymSpell is enabled and available."""
        return self._symspell_enabled and self._symspell is not None
    
    @property
    def ngram_enabled(self) -> bool:
        """Check if n-gram index is enabled and available."""
        return self._ngram_enabled and self._ngram is not None
    
    def _expand_ngram_terms(self, terms: List[str]) -> List[str]:
        """
        Expand terms using n-gram index.
        
        Handles:
        - Wildcard prefix search: "pyth*" → ["python", "pythonic", ...]
        - Substring matching (non-wildcard terms that aren't in vocab)
        
        Args:
            terms: List of query terms
            
        Returns:
            Expanded list of terms with wildcard matches included
        """
        if not self._ngram:
            return terms
        
        vocabulary = set(self.index.index.keys())
        expanded = []
        
        for term in terms:
            if term.endswith('*'):
                # Explicit wildcard: prefix search
                prefix = term[:-1].lower()
                if len(prefix) >= 2:
                    matches = self._ngram.search_prefix(prefix, max_results=10)
                    if matches:
                        # Add all matched terms
                        for match_term, similarity, freq in matches:
                            if match_term not in expanded:
                                expanded.append(match_term)
                    else:
                        # No matches, keep the prefix without wildcard
                        expanded.append(prefix)
                else:
                    expanded.append(term)
            elif term.lower() in vocabulary:
                # Exact match exists, keep it
                expanded.append(term)
            else:
                # Term not in vocabulary - try substring search
                matches = self._ngram.search_substring(term, max_results=5, min_similarity=0.5)
                if matches:
                    # Add original term plus top substring matches
                    expanded.append(term)
                    for match_term, similarity, freq in matches[:3]:
                        if match_term not in expanded:
                            expanded.append(match_term)
                else:
                    # No matches, keep original
                    expanded.append(term)
        
        return expanded
    
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
        
        return cls(index, pages_dir, index_path=index_path, **kwargs)
    
    def get_spelling_suggestion(self, query: str) -> Optional[str]:
        """
        Get spelling suggestion for a query.
        
        Uses SymSpell if available (faster, better suggestions), otherwise
        falls back to traditional edit-distance spellchecker.
        
        Args:
            query: The search query
            
        Returns:
            Suggested corrected query, or None if no correction needed
        """
        terms, phrases = parse_query(query)
        if not terms:
            return None
        
        # Use SymSpell if available (preferred)
        if self._symspell_enabled and self._symspell:
            corrected_terms = []
            has_correction = False
            vocabulary = set(self.index.index.keys())
            
            for term in terms:
                # Skip if term exists in vocabulary
                if term.lower() in vocabulary:
                    corrected_terms.append(term)
                    continue
                
                # Skip very short terms
                if len(term) < 3:
                    corrected_terms.append(term)
                    continue
                
                # Look up fuzzy matches
                matches = self._symspell.lookup(term, max_distance=2, max_results=1)
                if matches:
                    best_match, distance, _ = matches[0]
                    if distance > 0:
                        corrected_terms.append(best_match)
                        has_correction = True
                    else:
                        corrected_terms.append(term)
                else:
                    corrected_terms.append(term)
            
            if has_correction:
                # Reconstruct query with corrections
                # Preserve phrases in the suggestion
                suggestion_parts = corrected_terms[:]
                for phrase in phrases:
                    suggestion_parts.append(f'"{" ".join(phrase)}"')
                return ' '.join(suggestion_parts)
            
            return None
        
        # Fall back to traditional spellchecker
        if self._spellchecker:
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
        
        # Check cache first
        facet_key = tuple(sorted(facet_filters.items())) if facet_filters else None
        if self._cache:
            cached = self._cache.get(
                query, top_k=top_k, min_score=min_score, 
                highlight=highlight, snippet_length=snippet_length,
                facet_filters=facet_key, expand_synonyms=expand_synonyms
            )
            if cached is not None:
                # Restore metadata from cache
                results, metadata = cached
                self.last_suggestion = metadata.get('suggestion')
                self.last_facets = metadata.get('facets', {})
                self.last_expanded_query = metadata.get('expanded_query')
                return results
        
        # Parse query
        terms, phrases = parse_query(query)
        
        if not terms and not phrases:
            return []
        
        # Expand wildcard terms using n-gram index (e.g., "pyth*" → ["python", "pythonic"])
        ngram_expanded_terms = list(terms)
        if self.ngram_enabled:
            ngram_expanded_terms = self._expand_ngram_terms(terms)
        
        # Check for spelling suggestions (for "Did you mean?" display)
        # Uses SymSpell if available, falls back to traditional spellchecker
        suggestion = self.get_spelling_suggestion(query)
        if suggestion and suggestion.lower() != query.lower():
            self.last_suggestion = suggestion
        
        # Expand query with synonyms
        expanded_terms = list(ngram_expanded_terms)
        if expand_synonyms and self._synonyms and ngram_expanded_terms:
            expanded_terms = self._synonyms.expand_terms(ngram_expanded_terms, max_per_term=2)
            if expanded_terms != list(ngram_expanded_terms):
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
                'score': r.get('score', 0),
                'doc_type': r.get('doc_type', 'html')
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
        
        # Always try to provide suggestions when no results found
        if not results and not self.last_suggestion:
            suggestion = self.get_spelling_suggestion(query)
            if suggestion and suggestion.lower() != query.lower():
                self.last_suggestion = suggestion
        
        # Store in cache
        if self._cache:
            metadata = {
                'suggestion': self.last_suggestion,
                'facets': self.last_facets,
                'expanded_query': self.last_expanded_query
            }
            self._cache.set(
                query, (results, metadata),
                top_k=top_k, min_score=min_score,
                highlight=highlight, snippet_length=snippet_length,
                facet_filters=facet_key, expand_synonyms=expand_synonyms
            )
        
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
        
        .. deprecated:: 1.9.0
            Use :meth:`search` directly, which now returns ``List[Dict[str, Any]]``.
            This method will be removed in version 2.0.0.
        
        Migration:
            Replace ``engine.search_simple(query)`` with ``engine.search(query)``.
        """
        warnings.warn(
            "search_simple() is deprecated and will be removed in version 2.0.0. "
            "Use search() directly, which now returns List[Dict[str, Any]].",
            DeprecationWarning,
            stacklevel=2
        )
        return self.search(query, top_k=top_k, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get enhanced search engine statistics."""
        stats = super().get_stats()
        
        stats['features'] = {
            'spellcheck': self._spellcheck_enabled,
            'autocomplete': self._autocomplete_enabled,
            'facets': self._facets_enabled,
            'synonyms': self._synonyms_enabled,
            'symspell': self.symspell_enabled,
            'ngram': self.ngram_enabled
        }
        
        if self._autocomplete:
            stats['autocomplete_terms'] = self._autocomplete.get_word_count()
        
        if self._facets:
            stats['facet_stats'] = self._facets.get_stats()
        
        if self._synonyms:
            stats['synonym_groups'] = self._synonyms.get_synonym_count()
        
        if self._symspell:
            stats['symspell_stats'] = self._symspell.get_stats()
        
        if self._ngram:
            stats['ngram_stats'] = self._ngram.get_stats()
        
        return stats
