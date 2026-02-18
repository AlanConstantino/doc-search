"""
Search index building with BM25 scoring.
"""

import hashlib
import json
import gzip
import math
from operator import itemgetter
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Iterator

from .utils import tokenize
from .symspell import SymSpell
from .ngram import NGramIndex

import re

# Regex: valid suggestion terms are 2-40 chars, start with a letter,
# contain only letters/digits/hyphens, and aren't pure hex or IDs.
_VALID_TERM_RE = re.compile(r'^[a-z][a-z0-9\-]{1,24}$')
_HEX_LIKE_RE = re.compile(r'^[0-9a-f]{8,}$')
_ID_LIKE_RE = re.compile(r'^[a-z]\d{3,}')  # e.g. s000712340000925x, v35i6


def is_suggestion_worthy(term: str) -> bool:
    """Check if a term is clean enough for autocomplete/spellcheck suggestions.
    
    Filters out:
    - Too short (<2) or too long (>40)
    - Terms not starting with a letter
    - Hex-like strings (8+ hex chars)
    - ID-like strings (letter followed by 5+ digits)
    - Terms ending with underscore (variable-like: p_, x_, sum_)
    - Terms with no vowels (likely abbreviations/noise) unless very short
    """
    if not _VALID_TERM_RE.match(term):
        return False
    if _HEX_LIKE_RE.match(term):
        return False
    if _ID_LIKE_RE.match(term):
        return False
    if term.endswith('-'):
        return False
    # Reject terms with too many digits
    digit_count = sum(1 for c in term if c.isdigit())
    if digit_count > 0:
        letter_count = sum(1 for c in term if c.isalpha())
        # Need at least 3 letters per digit (e.g. "python3" ok, "v35i6" not)
        if letter_count < digit_count * 3:
            return False
    # Must contain at least one vowel if 5+ chars (filters junk like "bcdfx", "ngrmp")
    if len(term) >= 5 and not re.search(r'[aeiouy]', term):
        return False
    return True


def filter_suggestion_terms(doc_freqs: dict) -> dict:
    """Filter doc_freqs to only include suggestion-worthy terms."""
    return {term: freq for term, freq in doc_freqs.items() 
            if is_suggestion_worthy(term)}


class BM25Index:
    """
    BM25-based inverted index for document search.
    
    BM25 Parameters:
        k1: Term frequency saturation parameter (default: 1.5)
        b: Length normalization parameter (default: 0.75)
        stem: Whether to apply Porter stemming (default: True)
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75, stem: bool = True):
        # Validate BM25 parameters
        if k1 < 0:
            raise ValueError(f"k1 must be non-negative, got {k1}")
        if not (0 <= b <= 1):
            raise ValueError(f"b must be between 0 and 1, got {b}")
        
        self.k1 = k1
        self.b = b
        self.stem = stem
        
        # Document storage
        self.documents: Dict[int, Dict[str, Any]] = {}  # doc_id -> {url, title, ...}
        self.url_to_id: Dict[str, int] = {}  # url -> doc_id
        
        # Inverted index: term -> [(doc_id, term_frequency), ...]
        self.index: Dict[str, List[tuple]] = defaultdict(list)
        
        # Statistics
        self.doc_lengths: Dict[int, int] = {}  # doc_id -> document length in terms
        self.avg_doc_length: float = 0.0
        self.total_docs: int = 0
        
        # Term document frequencies
        self.doc_freqs: Dict[str, int] = defaultdict(int)  # term -> number of docs containing term
        
        # Content hashes for incremental indexing: url -> content hash
        self.content_hashes: Dict[str, str] = {}
    
    def add_document(self, doc_id: int, url: str, title: str, text: str, 
                     description: str = '', headings: List[tuple] = None,
                     doc_type: str = 'html'):
        """
        Add a document to the index.
        
        Args:
            doc_id: Unique document identifier
            url: Document URL
            title: Document title
            text: Document text content
            description: Optional meta description
            headings: Optional list of (level, text) tuples
            doc_type: Document type ('html', 'pdf', etc.)
        """
        # Build headings text for field-aware ranking
        headings_text = ''
        if headings:
            headings_text = ' '.join(text for _, text in headings)
        
        # Store document metadata (including headings for field-aware reranking)
        self.documents[doc_id] = {
            'url': url,
            'title': title,
            'description': description,
            'doc_type': doc_type,
            'headings_text': headings_text  # For field-aware ranking
        }
        self.url_to_id[url] = doc_id
        
        # Tokenize content (title gets more weight by being included multiple times)
        title_tokens = tokenize(title, apply_stemming=self.stem) * 3  # Title words count 3x
        heading_tokens = []
        if headings:
            for level, heading_text in headings:
                weight = max(1, 4 - level)  # h1=3x, h2=2x, h3+=1x
                heading_tokens.extend(tokenize(heading_text, apply_stemming=self.stem) * weight)
        
        text_tokens = tokenize(text, apply_stemming=self.stem)
        all_tokens = title_tokens + heading_tokens + text_tokens
        
        # Calculate term frequencies
        term_freqs: Dict[str, int] = defaultdict(int)
        for token in all_tokens:
            term_freqs[token] += 1
        
        # Store document length
        self.doc_lengths[doc_id] = len(all_tokens)
        
        # Update inverted index
        for term, freq in term_freqs.items():
            self.index[term].append((doc_id, freq))
            self.doc_freqs[term] += 1
        
        self.total_docs += 1
        
        # Update average document length
        self._update_avg_doc_length()
    
    def _update_avg_doc_length(self):
        """Recalculate average document length."""
        if self.doc_lengths:
            self.avg_doc_length = sum(self.doc_lengths.values()) / len(self.doc_lengths)
        else:
            self.avg_doc_length = 1.0  # Avoid division by zero
    
    def build_from_pages(self, pages_dir: Path, verbose: bool = True, parser: str = 'dom') -> int:
        """
        Build index from crawled page files.
        
        Args:
            pages_dir: Directory containing page JSON files
            verbose: Print progress messages
            parser: Parser for text extraction ('dom' or 'stream'). If raw_html
                    is available in page data, re-extracts using specified parser.
            
        Returns:
            Number of documents indexed
        """
        pages_dir = Path(pages_dir)
        page_files = list(pages_dir.glob('*.json'))
        total_files = len(page_files)
        
        if verbose:
            print(f"Indexing {total_files} pages (parser: {parser})...")
        
        # Import extractors
        from .parser import extract_text
        from .dom import extract_text_dom
        
        doc_id = 0
        reparsed_count = 0
        for i, page_file in enumerate(page_files):
            try:
                with open(page_file, 'r') as f:
                    page = json.load(f)
                
                # Re-extract from raw HTML if available
                if 'raw_html' in page and page['raw_html']:
                    if parser == 'dom':
                        extracted = extract_text_dom(page['raw_html'])
                    else:
                        extracted = extract_text(page['raw_html'])
                    text = extracted.get('text', '')
                    title = extracted.get('title', page.get('title', ''))
                    description = extracted.get('description', page.get('description', ''))
                    headings = extracted.get('headings', page.get('headings', []))
                    reparsed_count += 1
                else:
                    # Use pre-extracted text
                    text = page.get('text', '')
                    title = page.get('title', '')
                    description = page.get('description', '')
                    headings = page.get('headings', [])
                
                # Skip pages with no content
                if not text.strip():
                    continue
                
                self.add_document(
                    doc_id=doc_id,
                    url=page['url'],
                    title=title,
                    text=text,
                    description=description,
                    headings=headings,
                    doc_type=page.get('doc_type', 'html')
                )
                
                # Store content hash for incremental indexing
                hash_page = {'title': title, 'text': text, 'description': description, 'headings': headings}
                self.content_hashes[page['url']] = self._compute_content_hash(hash_page)
                
                doc_id += 1
                
                if verbose and (i + 1) % 500 == 0:
                    print(f"  Indexed {i + 1}/{total_files} pages...")
                    
            except (json.JSONDecodeError, IOError, KeyError) as e:
                if verbose:
                    print(f"  Warning: Skipping {page_file.name}: {e}")
                continue
        
        # Calculate average document length
        if self.doc_lengths:
            self.avg_doc_length = sum(self.doc_lengths.values()) / len(self.doc_lengths)
        
        if verbose:
            print(f"Indexing complete!")
            print(f"  Documents: {self.total_docs}")
            print(f"  Unique terms: {len(self.index)}")
            print(f"  Avg document length: {self.avg_doc_length:.1f} terms")
            if reparsed_count > 0:
                print(f"  Re-parsed from raw HTML: {reparsed_count}")
        
        return self.total_docs
    
    def remove_document(self, doc_id: int):
        """
        Remove a document from the index.
        
        Args:
            doc_id: Document ID to remove
        """
        if doc_id not in self.documents:
            return
        
        url = self.documents[doc_id]['url']
        
        # Remove from inverted index
        terms_to_remove = []
        for term, postings in self.index.items():
            original_len = len(postings)
            self.index[term] = [(did, freq) for did, freq in postings if did != doc_id]
            if len(self.index[term]) < original_len:
                self.doc_freqs[term] -= 1
                if self.doc_freqs[term] <= 0:
                    terms_to_remove.append(term)
        
        # Clean up empty terms
        for term in terms_to_remove:
            del self.index[term]
            del self.doc_freqs[term]
        
        # Remove from document storage
        del self.documents[doc_id]
        del self.url_to_id[url]
        del self.doc_lengths[doc_id]
        self.content_hashes.pop(url, None)
        
        self.total_docs -= 1
        self._update_avg_doc_length()
    
    @staticmethod
    def _compute_content_hash(page: dict) -> str:
        """Compute a hash of page content for change detection."""
        # Hash the fields that affect indexing
        content = json.dumps({
            'title': page.get('title', ''),
            'text': page.get('text', ''),
            'description': page.get('description', ''),
            'headings': page.get('headings', []),
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def build_from_pages_incremental(self, pages_dir: Path, verbose: bool = True,
                                      parser: str = 'dom') -> dict:
        """
        Incrementally update index from crawled page files.
        
        Only processes new/changed pages, removes deleted pages.
        
        Args:
            pages_dir: Directory containing page JSON files
            verbose: Print progress messages
            parser: Parser for text extraction ('dom' or 'stream')
            
        Returns:
            Dict with stats: {'new': int, 'updated': int, 'removed': int, 'unchanged': int}
        """
        from .parser import extract_text
        from .dom import extract_text_dom
        
        pages_dir = Path(pages_dir)
        page_files = list(pages_dir.glob('*.json'))
        
        if verbose:
            print(f"Incremental indexing from {len(page_files)} page files (parser: {parser})...")
        
        # Build mapping of url -> page data for current pages
        current_pages = {}  # url -> (page_data, file_path)
        for page_file in page_files:
            try:
                with open(page_file, 'r') as f:
                    page = json.load(f)
                
                # Re-extract from raw HTML if available
                if 'raw_html' in page and page['raw_html']:
                    if parser == 'dom':
                        extracted = extract_text_dom(page['raw_html'])
                    else:
                        extracted = extract_text(page['raw_html'])
                    page['text'] = extracted.get('text', '')
                    page['title'] = extracted.get('title', page.get('title', ''))
                    page['description'] = extracted.get('description', page.get('description', ''))
                    page['headings'] = extracted.get('headings', page.get('headings', []))
                
                if not page.get('text', '').strip():
                    continue
                
                current_pages[page['url']] = page
            except (json.JSONDecodeError, IOError, KeyError):
                continue
        
        current_urls = set(current_pages.keys())
        indexed_urls = set(self.content_hashes.keys())
        
        # Determine what changed
        new_urls = current_urls - indexed_urls
        removed_urls = indexed_urls - current_urls
        possibly_changed = current_urls & indexed_urls
        
        updated_urls = set()
        unchanged_urls = set()
        for url in possibly_changed:
            page = current_pages[url]
            new_hash = self._compute_content_hash(page)
            if new_hash != self.content_hashes.get(url):
                updated_urls.add(url)
            else:
                unchanged_urls.add(url)
        
        # Remove deleted pages
        for url in removed_urls:
            doc_id = self.url_to_id.get(url)
            if doc_id is not None:
                self.remove_document(doc_id)
        
        # Remove updated pages (will be re-added)
        for url in updated_urls:
            doc_id = self.url_to_id.get(url)
            if doc_id is not None:
                self.remove_document(doc_id)
        
        # Determine next doc_id
        next_doc_id = max(self.documents.keys()) + 1 if self.documents else 0
        
        # Add new and updated pages
        for url in sorted(new_urls | updated_urls):
            page = current_pages[url]
            self.add_document(
                doc_id=next_doc_id,
                url=page['url'],
                title=page.get('title', ''),
                text=page.get('text', ''),
                description=page.get('description', ''),
                headings=page.get('headings', []),
                doc_type=page.get('doc_type', 'html')
            )
            self.content_hashes[url] = self._compute_content_hash(page)
            next_doc_id += 1
        
        stats = {
            'new': len(new_urls),
            'updated': len(updated_urls),
            'removed': len(removed_urls),
            'unchanged': len(unchanged_urls),
        }
        
        if verbose:
            print(f"Incremental indexing complete!")
            print(f"  {stats['new']} new, {stats['updated']} updated, "
                  f"{stats['removed']} removed, {stats['unchanged']} unchanged")
            print(f"  Total documents: {self.total_docs}")
            print(f"  Unique terms: {len(self.index)}")
        
        return stats
    
    def _idf(self, term: str) -> float:
        """Calculate IDF for a term using BM25 formula."""
        n = self.total_docs
        df = self.doc_freqs.get(term, 0)
        
        if df == 0:
            return 0.0
        
        # BM25 IDF formula
        return math.log((n - df + 0.5) / (df + 0.5) + 1)
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search the index using BM25 scoring.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            
        Returns:
            List of result dicts with 'url', 'title', 'description', 'score'
        """
        query_terms = tokenize(query, apply_stemming=self.stem)
        
        if not query_terms:
            return []
        
        # Calculate scores for all documents containing any query term
        scores: Dict[int, float] = defaultdict(float)
        
        # Guard against zero avg_doc_length
        avg_dl = self.avg_doc_length if self.avg_doc_length > 0 else 1.0
        
        # Pre-compute constants for BM25 formula
        k1 = self.k1
        b = self.b
        k1_plus_1 = k1 + 1
        one_minus_b = 1 - b
        b_div_avg_dl = b / avg_dl
        
        # Cache doc_lengths for faster lookup
        doc_lengths = self.doc_lengths
        index = self.index
        
        for term in query_terms:
            postings = index.get(term)
            if postings is None:
                continue
            
            idf = self._idf(term)
            
            for doc_id, term_freq in postings:
                doc_length = doc_lengths[doc_id]
                
                # BM25 scoring formula (optimized)
                numerator = term_freq * k1_plus_1
                denominator = term_freq + k1 * (one_minus_b + b_div_avg_dl * doc_length)
                
                scores[doc_id] += idf * (numerator / denominator)
        
        # Sort by score and get top results using itemgetter (faster than lambda)
        sorted_docs = sorted(scores.items(), key=itemgetter(1), reverse=True)[:top_k]
        
        # Build results with cached document lookups
        documents = self.documents
        results = []
        for doc_id, score in sorted_docs:
            doc = documents[doc_id]
            results.append({
                'url': doc['url'],
                'title': doc['title'],
                'description': doc['description'],
                'score': round(score, 4),
                'doc_type': doc.get('doc_type', 'html')
            })
        
        return results
    
    def save(self, filepath: Path, compress: bool = True):
        """
        Save index to disk.
        
        Args:
            filepath: Output file path
            compress: Use gzip compression
        """
        filepath = Path(filepath)
        
        data = {
            'k1': self.k1,
            'b': self.b,
            'stem': self.stem,
            'documents': self.documents,
            'url_to_id': self.url_to_id,
            'index': {term: postings for term, postings in self.index.items()},
            'doc_lengths': {str(k): v for k, v in self.doc_lengths.items()},
            'avg_doc_length': self.avg_doc_length,
            'total_docs': self.total_docs,
            'doc_freqs': dict(self.doc_freqs),
            'content_hashes': self.content_hashes
        }
        
        json_data = json.dumps(data)
        
        if compress:
            filepath = filepath.with_suffix('.json.gz')
            with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                f.write(json_data)
        else:
            with open(filepath, 'w') as f:
                f.write(json_data)
        
        return filepath
    
    @classmethod
    def load(cls, filepath: Path) -> 'BM25Index':
        """
        Load index from disk.
        
        Args:
            filepath: Input file path
            
        Returns:
            Loaded BM25Index instance
        """
        filepath = Path(filepath)
        
        # Check for compressed version
        if filepath.suffix == '.gz':
            with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                data = json.load(f)
        elif filepath.with_suffix('.json.gz').exists():
            with gzip.open(filepath.with_suffix('.json.gz'), 'rt', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(filepath, 'r') as f:
                data = json.load(f)
        
        # Create instance
        index = cls(k1=data['k1'], b=data['b'], stem=data.get('stem', True))
        
        # Restore state
        index.documents = {int(k): v for k, v in data['documents'].items()}
        index.url_to_id = data['url_to_id']
        index.index = defaultdict(list, {k: [tuple(p) for p in v] for k, v in data['index'].items()})
        index.doc_lengths = {int(k): v for k, v in data['doc_lengths'].items()}
        index.avg_doc_length = data['avg_doc_length']
        index.total_docs = data['total_docs']
        index.doc_freqs = defaultdict(int, data['doc_freqs'])
        index.content_hashes = data.get('content_hashes', {})
        
        return index
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            'total_documents': self.total_docs,
            'unique_terms': len(self.index),
            'avg_document_length': round(self.avg_doc_length, 1),
            'k1': self.k1,
            'b': self.b,
            'stemming': self.stem
        }
    
    def build_symspell(self, max_distance: int = 2) -> SymSpell:
        """
        Build a SymSpell fuzzy matching index from the vocabulary.
        
        Uses document frequency as word frequency for ranking suggestions.
        
        Args:
            max_distance: Maximum edit distance for fuzzy matching
            
        Returns:
            SymSpell instance populated with vocabulary
        """
        symspell = SymSpell(max_distance=max_distance)
        
        clean_terms = filter_suggestion_terms(self.doc_freqs)
        for term, doc_freq in clean_terms.items():
            symspell.add_word(term, frequency=doc_freq)
        
        return symspell
    
    def build_ngram_index(self, n: int = 3) -> NGramIndex:
        """
        Build an n-gram index from the vocabulary.
        
        Enables prefix search (term*) and substring matching.
        
        Args:
            n: Size of n-grams (default: 3 for trigrams)
            
        Returns:
            NGramIndex instance populated with vocabulary
        """
        ngram_index = NGramIndex(n=n)
        
        clean_terms = filter_suggestion_terms(self.doc_freqs)
        for term, doc_freq in clean_terms.items():
            ngram_index.add_term(term, frequency=doc_freq)
        
        return ngram_index
    
    def get_doc_id(self, url: str) -> Optional[int]:
        """
        Get the document ID for a given URL.
        
        Args:
            url: The document URL
            
        Returns:
            Document ID if found, None otherwise
        """
        return self.url_to_id.get(url)
    
    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """
        Get document metadata by document ID.
        
        Args:
            doc_id: The document ID
            
        Returns:
            Document dict with 'url', 'title', 'description' if found, None otherwise
        """
        return self.documents.get(doc_id)
    
    def get_document_frequency(self, term: str) -> Optional[int]:
        """
        Get the document frequency for a term (number of documents containing it).
        
        Args:
            term: The term to look up (should be lowercase)
            
        Returns:
            Number of documents containing the term, or None if not in index
        """
        postings = self.index.get(term.lower())
        if postings is None:
            return None
        return len(postings)
    
    def has_url(self, url: str) -> bool:
        """
        Check if a URL is in the index.
        
        Args:
            url: The URL to check
            
        Returns:
            True if URL is indexed, False otherwise
        """
        return url in self.url_to_id
