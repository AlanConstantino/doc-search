# API Reference

This document provides comprehensive API documentation for using doc-search as a Python library. For command-line usage, see the [README](../README.md). For architecture details, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Classes](#core-classes)
  - [BM25Index](#bm25index)
  - [SearchEngine](#searchengine)
  - [EnhancedSearchEngine](#enhancedsearchengine)
  - [Crawler](#crawler)
- [Utility Functions](#utility-functions)
- [Common Patterns](#common-patterns)
- [Type Reference](#type-reference)

---

## Installation

```bash
# Clone and install
git clone https://github.com/AlanConstantino/doc-search.git
cd doc-search

# Use directly (no pip install required)
python -m doc_search --help
```

For library usage, add the package to your Python path or install in development mode.

---

## Quick Start

### Basic Search (Existing Index)

```python
from doc_search.search import SearchEngine

# Load an existing index
engine = SearchEngine.load('/path/to/index.json.gz')

# Search
results = engine.search('python list comprehension', top_k=10)

for result in results:
    print(f"{result['title']}: {result['url']}")
    print(f"  Score: {result['score']}")
    print(f"  {result['snippet']}\n")
```

### Full Pipeline (Crawl → Index → Search)

```python
from pathlib import Path
from doc_search.crawl import Crawler
from doc_search.index import BM25Index
from doc_search.search import EnhancedSearchEngine

# 1. Crawl a documentation site
crawler = Crawler(
    base_url='https://docs.python.org/3/',
    data_dir=Path('./python-docs'),
    max_pages=100,
    verbose=True
)
crawler.crawl()

# 2. Build search index
index = BM25Index()
index.build_from_pages(Path('./python-docs/pages'))
index.save(Path('./python-docs/index.json.gz'))

# 3. Search
engine = EnhancedSearchEngine(index, pages_dir=Path('./python-docs/pages'))
results = engine.search('async await', top_k=5)
```

---

## Core Classes

### BM25Index

The `BM25Index` class implements a BM25-based inverted index for full-text search. BM25 (Best Matching 25) is an industry-standard ranking algorithm used by Elasticsearch and Apache Lucene.

#### Class Definition

```python
class BM25Index:
    """BM25-based inverted index for document search."""
    
    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        stem: bool = True
    )
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `k1` | `float` | `1.5` | Term frequency saturation. Higher values give more weight to term frequency. Range: 0+ |
| `b` | `float` | `0.75` | Length normalization. 0 = no normalization, 1 = full normalization. Range: 0-1 |
| `stem` | `bool` | `True` | Whether to apply Porter stemming to tokens |

#### Methods

##### `add_document`

Add a single document to the index.

```python
def add_document(
    self,
    doc_id: int,
    url: str,
    title: str,
    text: str,
    description: str = '',
    headings: List[Tuple[int, str]] = None
) -> None
```

**Parameters:**
- `doc_id`: Unique integer identifier for the document
- `url`: Document URL (used for deduplication and retrieval)
- `title`: Document title (weighted 3x in scoring)
- `text`: Full text content
- `description`: Optional meta description
- `headings`: Optional list of `(level, text)` tuples where level is 1-6

**Example:**
```python
index = BM25Index()
index.add_document(
    doc_id=0,
    url='https://example.com/intro',
    title='Introduction to Python',
    text='Python is a programming language...',
    description='Learn Python basics',
    headings=[(1, 'Getting Started'), (2, 'Installation')]
)
```

##### `build_from_pages`

Build index from a directory of crawled page JSON files.

```python
def build_from_pages(
    self,
    pages_dir: Path,
    verbose: bool = True
) -> int
```

**Parameters:**
- `pages_dir`: Path to directory containing `*.json` page files
- `verbose`: Print progress messages

**Returns:** Number of documents indexed

**Example:**
```python
index = BM25Index()
num_docs = index.build_from_pages(Path('./site/pages'))
print(f"Indexed {num_docs} documents")
```

##### `search`

Search the index and return ranked results.

```python
def search(
    self,
    query: str,
    top_k: int = 10
) -> List[Dict[str, Any]]
```

**Parameters:**
- `query`: Search query string
- `top_k`: Maximum number of results to return

**Returns:** List of result dictionaries:
```python
{
    'url': str,         # Document URL
    'title': str,       # Document title
    'description': str, # Meta description
    'score': float      # BM25 relevance score
}
```

**Example:**
```python
results = index.search('list comprehension', top_k=5)
for r in results:
    print(f"{r['score']:.4f}: {r['title']}")
```

##### `save` / `load`

Persist and restore the index.

```python
def save(self, filepath: Path, compress: bool = True) -> Path

@classmethod
def load(cls, filepath: Path) -> 'BM25Index'
```

**Example:**
```python
# Save (compressed by default)
index.save(Path('./index.json.gz'))

# Load
index = BM25Index.load(Path('./index.json.gz'))
```

##### `get_stats`

Get index statistics.

```python
def get_stats(self) -> Dict[str, Any]
```

**Returns:**
```python
{
    'total_documents': int,       # Number of indexed documents
    'unique_terms': int,          # Vocabulary size
    'avg_document_length': float, # Average tokens per document
    'k1': float,                  # BM25 k1 parameter
    'b': float,                   # BM25 b parameter
    'stemming': bool              # Whether stemming is enabled
}
```

##### Lookup Methods

```python
def get_doc_id(self, url: str) -> Optional[int]
def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]
def has_url(self, url: str) -> bool
```

---

### SearchEngine

The `SearchEngine` class provides a high-level search interface with phrase search support and snippet highlighting.

#### Class Definition

```python
class SearchEngine:
    """High-level search interface with phrase search and snippet highlighting."""
    
    def __init__(
        self,
        index: BM25Index,
        pages_dir: Optional[Path] = None
    )
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `index` | `BM25Index` | Required | The search index |
| `pages_dir` | `Path \| None` | `None` | Directory containing page JSON files (enables snippet generation) |

#### Class Methods

##### `load`

Load a search engine from a saved index file.

```python
@classmethod
def load(cls, index_path: Path) -> 'SearchEngine'
```

**Example:**
```python
engine = SearchEngine.load(Path('./site/index.json.gz'))
```

#### Methods

##### `search`

Search with phrase support and highlighted snippets.

```python
def search(
    self,
    query: str,
    top_k: int = 10,
    min_score: float = 0.0,
    highlight: bool = True,
    snippet_length: int = 150
) -> List[Dict[str, Any]]
```

**Parameters:**
- `query`: Search query. Supports:
  - Regular terms: `python tutorial`
  - Exact phrases: `"list comprehension"`
  - Mixed: `python "list comprehension" tutorial`
- `top_k`: Maximum number of results
- `min_score`: Minimum BM25 score threshold
- `highlight`: Whether to highlight query terms in snippets with `<mark>` tags
- `snippet_length`: Target snippet length in characters

**Returns:** List of result dictionaries:
```python
{
    'url': str,         # Document URL
    'title': str,       # Document title
    'snippet': str,     # Highlighted snippet
    'description': str, # Original meta description
    'score': float      # BM25 score
}
```

**Example:**
```python
# Basic search
results = engine.search('async programming')

# Phrase search
results = engine.search('"context manager"')

# Combined
results = engine.search('python "with statement" example', top_k=5)
```

##### `get_document`

Get document metadata by URL.

```python
def get_document(self, url: str) -> Optional[Dict[str, Any]]
```

##### `get_stats`

Get search engine statistics.

```python
def get_stats(self) -> Dict[str, Any]
```

---

### EnhancedSearchEngine

The `EnhancedSearchEngine` extends `SearchEngine` with additional features: spell checking, autocomplete, faceted search, and synonym expansion.

#### Class Definition

```python
class EnhancedSearchEngine(SearchEngine):
    """Enhanced search with spell check, autocomplete, facets, and synonyms."""
    
    def __init__(
        self,
        index: BM25Index,
        pages_dir: Optional[Path] = None,
        enable_spellcheck: bool = True,
        enable_autocomplete: bool = True,
        enable_facets: bool = True,
        enable_synonyms: bool = False,
        synonym_groups: Optional[List[Set[str]]] = None
    )
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `index` | `BM25Index` | Required | The search index |
| `pages_dir` | `Path \| None` | `None` | Directory for snippet generation |
| `enable_spellcheck` | `bool` | `True` | Enable "Did you mean..." suggestions |
| `enable_autocomplete` | `bool` | `True` | Enable type-ahead suggestions |
| `enable_facets` | `bool` | `True` | Enable faceted search |
| `enable_synonyms` | `bool` | `False` | Enable query expansion with synonyms |
| `synonym_groups` | `List[Set[str]] \| None` | `None` | Custom synonym groups |

#### Methods

##### `search`

Enhanced search with additional features. Returns `List[Dict[str, Any]]` for compatibility with `SearchEngine`.

```python
def search(
    self,
    query: str,
    top_k: int = 10,
    min_score: float = 0.0,
    highlight: bool = True,
    snippet_length: int = 150,
    facet_filters: Optional[Dict[str, str]] = None,
    expand_synonyms: bool = True
) -> List[Dict[str, Any]]
```

**Additional Parameters:**
- `facet_filters`: Filter results by facet values (e.g., `{'section': 'library'}`)
- `expand_synonyms`: Whether to expand query with synonyms (if enabled)

**Instance Attributes (after search):**
After calling `search()`, these attributes contain metadata:
- `last_suggestion`: Spelling correction suggestion (or `None`)
- `last_facets`: Facet counts for the result set
- `last_expanded_query`: Query with synonym expansion (or `None`)

**Example:**
```python
engine = EnhancedSearchEngine.load(Path('./index.json.gz'))

results = engine.search('pyton list')  # Typo in "python"

if engine.last_suggestion:
    print(f"Did you mean: {engine.last_suggestion}?")

print(f"Facets: {engine.last_facets}")
```

##### `search_enhanced`

Returns a dict containing both results and metadata.

```python
def search_enhanced(
    self,
    query: str,
    top_k: int = 10,
    min_score: float = 0.0,
    highlight: bool = True,
    snippet_length: int = 150,
    facet_filters: Optional[Dict[str, str]] = None,
    expand_synonyms: bool = True
) -> Dict[str, Any]
```

**Returns:**
```python
{
    'results': List[Dict],       # Search results
    'suggestion': str | None,    # Spelling suggestion
    'facets': Dict[str, Dict],   # Facet counts
    'query': str,                # Original query
    'expanded_query': str | None # Query with synonyms
}
```

**Example:**
```python
response = engine.search_enhanced('pyton decorators')

print(f"Query: {response['query']}")
if response['suggestion']:
    print(f"Did you mean: {response['suggestion']}?")
    
for result in response['results']:
    print(f"- {result['title']}")
```

##### `get_spelling_suggestion`

Get spelling suggestion for a query.

```python
def get_spelling_suggestion(self, query: str) -> Optional[str]
```

##### `get_suggestions`

Get type-ahead suggestions for a prefix.

```python
def get_suggestions(
    self,
    prefix: str,
    max_suggestions: int = 10
) -> List[str]
```

**Example:**
```python
suggestions = engine.get_suggestions('dec', max_suggestions=5)
# ['decorator', 'decimal', 'decode', 'decoding', 'declare']
```

##### `get_facet_counts`

Get facet counts for filtering.

```python
def get_facet_counts(
    self,
    results: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Dict[str, int]]
```

**Returns:** Nested dict mapping `facet_type -> value -> count`

**Example:**
```python
# Get all facet counts
all_facets = engine.get_facet_counts()

# Get facets for specific results
results = engine.search('async')
result_facets = engine.get_facet_counts(results)
```

---

### Crawler

The `Crawler` class provides web crawling with politeness controls, resumable state, and parallel fetching.

#### Class Definition

```python
class Crawler:
    """Web crawler with politeness controls, resumable crawling, and parallel fetching."""
    
    USER_AGENT = "DocSearchBot/1.2 (+https://github.com/AlanConstantino/doc-search)"
    
    def __init__(
        self,
        base_url: str,
        data_dir: Path,
        delay: float = 1.0,
        timeout: float = 30.0,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        auth: Optional[Tuple[str, str]] = None,
        auth_token: Optional[str] = None,
        stay_on_domain: bool = True,
        same_path: bool = False,
        url_filter: Optional[Callable[[str], bool]] = None,
        verbose: bool = True,
        workers: int = 1,
        extract_docs: bool = False,
        incremental: bool = False
    )
```

#### Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | Required | Starting URL for crawl |
| `data_dir` | `Path` | Required | Directory for storing crawled data |
| `delay` | `float` | `1.0` | Seconds between requests (per domain) |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `max_pages` | `int \| None` | `None` | Maximum pages to crawl |
| `max_depth` | `int \| None` | `None` | Maximum link depth from start |
| `auth` | `Tuple[str, str] \| None` | `None` | HTTP Basic Auth `(username, password)` |
| `auth_token` | `str \| None` | `None` | Pre-encoded Base64 auth token |
| `stay_on_domain` | `bool` | `True` | Only crawl URLs on the same domain |
| `same_path` | `bool` | `False` | Only crawl URLs under the starting path |
| `url_filter` | `Callable[[str], bool] \| None` | `None` | Custom URL filter function |
| `verbose` | `bool` | `True` | Print progress messages |
| `workers` | `int` | `1` | Number of parallel fetch workers |
| `extract_docs` | `bool` | `False` | Extract text from PDFs |
| `incremental` | `bool` | `False` | Only re-download changed pages |

#### Methods

##### `crawl`

Start or resume crawling.

```python
def crawl(self, resume: bool = True) -> Dict[str, Any]
```

**Parameters:**
- `resume`: If `True`, resume from saved state if available

**Returns:** Statistics dictionary:
```python
{
    'pages_crawled': int,
    'pages_skipped': int,
    'pages_failed': int,
    'bytes_downloaded': int,
    'elapsed_seconds': float,
    'pages_per_minute': float,
    'pending_urls': int,
    'unique_urls_seen': int
}
```

**Example:**
```python
crawler = Crawler(
    base_url='https://docs.python.org/3/',
    data_dir=Path('./python-docs'),
    max_pages=1000,
    workers=4
)
stats = crawler.crawl()
print(f"Crawled {stats['pages_crawled']} pages")
```

##### `get_crawled_pages`

Generator yielding all crawled page data.

```python
def get_crawled_pages(
    self,
    warn_on_error: bool = True
) -> Iterator[Dict[str, Any]]
```

**Yields:** Page dictionaries:
```python
{
    'url': str,
    'title': str,
    'text': str,
    'description': str,
    'headings': List[Tuple[int, str]],
    'depth': int,
    'crawled_at': float
}
```

**Example:**
```python
for page in crawler.get_crawled_pages():
    print(f"Crawled: {page['title']}")
```

#### Crawl Behavior

**Politeness Controls:**
- Respects `robots.txt` directives
- Honors `Crawl-delay` from robots.txt
- Per-domain rate limiting (even with multiple workers)
- Backs off on HTTP 429 (rate limited)

**URL Filtering:**
- Skips non-HTML files (images, archives, etc.)
- Skips common non-documentation paths (`/download/`, `/releases/`, etc.)
- Custom filtering via `url_filter` parameter

**State Persistence:**
- Saves checkpoint every 100 pages
- Resumes automatically on interruption
- Incremental mode only re-fetches changed content

---

## Utility Functions

### Tokenization

```python
from doc_search.core import tokenize

def tokenize(
    text: str,
    apply_stemming: bool = False
) -> List[str]
```

Tokenizes text for indexing and search:
1. Converts to lowercase
2. Extracts words (letters, digits, underscores)
3. Removes stop words
4. Optionally applies Porter stemming

**Example:**
```python
>>> tokenize("The quick brown fox")
['quick', 'brown', 'fox']

>>> tokenize("Python3 programming is fun!")
['python3', 'programming', 'fun']

>>> tokenize("running files", apply_stemming=True)
['run', 'file']
```

### URL Utilities

```python
from doc_search.core import normalize_url, get_domain, is_same_domain

# Normalize URL for deduplication
url = normalize_url('https://Example.COM/path/../page#section')
# 'https://example.com/page'

# Extract domain
domain = get_domain('https://docs.python.org/3/library/')
# 'docs.python.org'

# Check same domain
is_same_domain('https://example.com/a', 'https://example.com/b')
# True
```

### Terminal Colors

```python
from doc_search.app.terminal import Colors, colorize

# Direct color codes
print(Colors.BOLD + "Bold text" + Colors.RESET)

# Using colorize()
print(colorize("Error!", Colors.RED, Colors.BOLD))

# Convenience functions
from doc_search.app.terminal import style_title, style_url, style_error
print(style_title("My Title"))
print(style_url("https://example.com"))
print(style_error("Something went wrong"))
```

---

## Common Patterns

### Custom URL Filtering

```python
def my_filter(url: str) -> bool:
    """Only crawl English documentation."""
    return '/en/' in url or url.endswith('/en')

crawler = Crawler(
    base_url='https://docs.example.com/',
    data_dir=Path('./data'),
    url_filter=my_filter
)
```

### Authenticated Crawling

```python
# Using username/password
crawler = Crawler(
    base_url='https://internal.docs.com/',
    data_dir=Path('./data'),
    auth=('username', 'password')
)

# Using pre-encoded token
crawler = Crawler(
    base_url='https://internal.docs.com/',
    data_dir=Path('./data'),
    auth_token='dXNlcm5hbWU6cGFzc3dvcmQ='
)
```

### Incremental Updates

```python
# First crawl
crawler = Crawler(
    base_url='https://docs.example.com/',
    data_dir=Path('./data'),
    incremental=False
)
crawler.crawl()

# Later: only fetch changed pages
crawler = Crawler(
    base_url='https://docs.example.com/',
    data_dir=Path('./data'),
    incremental=True
)
crawler.crawl()  # Uses ETags and content hashes
```

### Building a Search API

```python
from flask import Flask, request, jsonify
from doc_search.search import EnhancedSearchEngine

app = Flask(__name__)
engine = EnhancedSearchEngine.load('./index.json.gz')

@app.route('/search')
def search():
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 10))
    
    response = engine.search_enhanced(query, top_k=limit)
    return jsonify(response)

@app.route('/autocomplete')
def autocomplete():
    prefix = request.args.get('q', '')
    suggestions = engine.get_suggestions(prefix)
    return jsonify(suggestions)
```

### Tuning BM25 Parameters

```python
# Default parameters (good for general use)
index = BM25Index(k1=1.5, b=0.75)

# For short documents (e.g., API reference)
# Lower b reduces length normalization penalty
index = BM25Index(k1=1.5, b=0.5)

# For long documents (e.g., tutorials)
# Higher k1 increases term frequency saturation
index = BM25Index(k1=2.0, b=0.75)

# Disable stemming for exact matching
index = BM25Index(stem=False)
```

### Custom Synonyms

```python
from doc_search.search import EnhancedSearchEngine

# Define custom synonym groups
synonyms = [
    {'error', 'exception', 'bug'},
    {'function', 'method', 'procedure'},
    {'class', 'type', 'object'},
]

engine = EnhancedSearchEngine(
    index=index,
    enable_synonyms=True,
    synonym_groups=synonyms
)
```

---

## Type Reference

### Result Dictionary

```python
# Basic search result
{
    'url': str,         # Document URL
    'title': str,       # Document title
    'description': str, # Meta description
    'score': float      # BM25 relevance score (0+)
}

# Enhanced search result (with snippets)
{
    'url': str,
    'title': str,
    'snippet': str,     # Highlighted text snippet
    'description': str,
    'score': float,
    'facets': Dict[str, str]  # Optional facet values
}
```

### Page Data (from Crawler)

```python
{
    'url': str,
    'title': str,
    'text': str,               # Full extracted text
    'description': str,
    'headings': List[Tuple[int, str]],  # [(level, text), ...]
    'depth': int,              # Link depth from start URL
    'crawled_at': float,       # Unix timestamp
    'etag': Optional[str],     # HTTP ETag (incremental)
    'last_modified': Optional[str],  # HTTP Last-Modified
    'content_hash': str        # SHA256 of content
}
```

### Statistics Dictionary

```python
# BM25Index.get_stats()
{
    'total_documents': int,
    'unique_terms': int,
    'avg_document_length': float,
    'k1': float,
    'b': float,
    'stemming': bool
}

# EnhancedSearchEngine.get_stats()
{
    'total_documents': int,
    'unique_terms': int,
    'avg_document_length': float,
    'k1': float,
    'b': float,
    'stemming': bool,
    'features': {
        'spellcheck': bool,
        'autocomplete': bool,
        'facets': bool,
        'synonyms': bool
    },
    'autocomplete_terms': int,  # If enabled
    'facet_stats': Dict,        # If enabled
    'synonym_groups': int       # If enabled
}

# Crawler.crawl() return value
{
    'pages_crawled': int,
    'pages_skipped': int,
    'pages_failed': int,
    'pages_unchanged': int,     # Incremental mode
    'bytes_downloaded': int,
    'elapsed_seconds': float,
    'pages_per_minute': float,
    'pending_urls': int,
    'unique_urls_seen': int
}
```

---

## Class Relationships

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Core Components                              │
└─────────────────────────────────────────────────────────────────────┘

  Crawler                    BM25Index                 SearchEngine
     │                           │                          │
     │ crawl()                   │ search()                 │ search()
     │ ──────▶ pages/*.json      │ ◀───────────────────────▶│
     │                           │                          │
     │                   ┌───────┴───────┐                  │
     │                   │               │                  │
     ▼                   ▼               ▼                  ▼
  ┌──────────┐     ┌──────────┐    ┌──────────┐    ┌──────────────────┐
  │CrawlState│     │ tokenize │    │   stem   │    │EnhancedSearchEngine│
  │RateLimiter│    │(core)    │    │(stemmer) │    │                  │
  │RobotsCheck│    └──────────┘    └──────────┘    │  ├─SpellChecker  │
  └──────────┘                                      │  ├─Autocomplete  │
                                                    │  ├─FacetIndex    │
                                                    │  └─SynonymExpander│
                                                    └──────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         Data Flow                                    │
└─────────────────────────────────────────────────────────────────────┘

  Website ──▶ Crawler ──▶ pages/*.json ──▶ BM25Index ──▶ SearchEngine
                              │                │              │
                              │                │              │
                              ▼                ▼              ▼
                          (raw text)    (index.json.gz)  (search results)
```

---

## See Also

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture and module organization
- [TOKENIZATION.md](./TOKENIZATION.md) - Details on text tokenization
- [OPERATOR_GUIDE.md](./OPERATOR_GUIDE.md) - Deployment and operations guide
