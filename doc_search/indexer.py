"""
Search index building with BM25 scoring.
"""

import json
import gzip
import math
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Iterator

from .utils import tokenize


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
    
    def add_document(self, doc_id: int, url: str, title: str, text: str, 
                     description: str = '', headings: List[tuple] = None):
        """
        Add a document to the index.
        
        Args:
            doc_id: Unique document identifier
            url: Document URL
            title: Document title
            text: Document text content
            description: Optional meta description
            headings: Optional list of (level, text) tuples
        """
        # Store document metadata
        self.documents[doc_id] = {
            'url': url,
            'title': title,
            'description': description
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
    
    def build_from_pages(self, pages_dir: Path, verbose: bool = True) -> int:
        """
        Build index from crawled page files.
        
        Args:
            pages_dir: Directory containing page JSON files
            verbose: Print progress messages
            
        Returns:
            Number of documents indexed
        """
        pages_dir = Path(pages_dir)
        page_files = list(pages_dir.glob('*.json'))
        total_files = len(page_files)
        
        if verbose:
            print(f"Indexing {total_files} pages...")
        
        doc_id = 0
        for i, page_file in enumerate(page_files):
            try:
                with open(page_file, 'r') as f:
                    page = json.load(f)
                
                # Skip pages with no content
                if not page.get('text', '').strip():
                    continue
                
                self.add_document(
                    doc_id=doc_id,
                    url=page['url'],
                    title=page.get('title', ''),
                    text=page.get('text', ''),
                    description=page.get('description', ''),
                    headings=page.get('headings', [])
                )
                
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
        
        return self.total_docs
    
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
        
        for term in query_terms:
            if term not in self.index:
                continue
            
            idf = self._idf(term)
            
            for doc_id, term_freq in self.index[term]:
                doc_length = self.doc_lengths[doc_id]
                
                # BM25 scoring formula
                numerator = term_freq * (self.k1 + 1)
                denominator = term_freq + self.k1 * (
                    1 - self.b + self.b * (doc_length / avg_dl)
                )
                
                scores[doc_id] += idf * (numerator / denominator)
        
        # Sort by score and get top results
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        results = []
        for doc_id, score in sorted_docs:
            doc = self.documents[doc_id]
            results.append({
                'url': doc['url'],
                'title': doc['title'],
                'description': doc['description'],
                'score': round(score, 4)
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
            'doc_freqs': dict(self.doc_freqs)
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
    
    def has_url(self, url: str) -> bool:
        """
        Check if a URL is in the index.
        
        Args:
            url: The URL to check
            
        Returns:
            True if URL is indexed, False otherwise
        """
        return url in self.url_to_id
