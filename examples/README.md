# doc-search Examples

This directory contains example scripts demonstrating how to use doc-search programmatically.

## Prerequisites

All examples assume you're running from the repository root directory:

```bash
cd /path/to/doc-search
```

## Examples

### 1. Basic Crawling (`basic_crawl.py`)

Demonstrates how to crawl a documentation site programmatically.

```bash
python examples/basic_crawl.py
```

**What it shows:**
- Creating a `Crawler` instance
- Configuring crawl options (delay, max pages, etc.)
- Running a crawl and accessing statistics
- Resuming interrupted crawls

### 2. Building an Index (`build_index.py`)

Demonstrates how to build a BM25 search index from crawled pages.

```bash
python examples/build_index.py
```

**What it shows:**
- Creating a `BM25Index` instance
- Adding documents manually
- Building an index from crawled page files
- Configuring BM25 parameters (k1, b, stemming)
- Saving and loading indexes

### 3. Searching Programmatically (`search_example.py`)

Demonstrates how to search an existing index using the search API.

```bash
python examples/search_example.py
```

**What it shows:**
- Loading an existing index
- Using `SearchEngine` for basic search
- Using `EnhancedSearchEngine` for advanced features
- Phrase search with `"quoted terms"`
- Getting spelling suggestions
- Autocomplete suggestions
- Faceted search

### 4. Full Pipeline Demo (`full_pipeline.py`)

A complete end-to-end demonstration of the crawl → index → search workflow.

```bash
python examples/full_pipeline.py
```

**What it shows:**
- Complete workflow from scratch
- Using temporary directories for demo purposes
- All three stages integrated together
- Cleanup and error handling

## API Quick Reference

### Crawler

```python
from doc_search.crawl import Crawler
from pathlib import Path

crawler = Crawler(
    base_url="https://docs.example.com",
    data_dir=Path("/path/to/store/data"),
    delay=1.0,           # Seconds between requests
    max_pages=100,       # Limit pages to crawl
    max_depth=5,         # Maximum link depth
    workers=1,           # Parallel workers
    extract_docs=False,  # Extract PDF text
    verbose=True
)

stats = crawler.crawl(resume=True)  # resume=False to start fresh
```

### BM25Index

```python
from doc_search.index import BM25Index
from pathlib import Path

# Build from crawled pages
index = BM25Index(k1=1.5, b=0.75, stem=True)
num_docs = index.build_from_pages(Path("site_dir/pages"))

# Or add documents manually
index.add_document(
    doc_id=0,
    url="https://example.com/page",
    title="Page Title",
    text="Page content here...",
    description="Meta description"
)

# Save and load
index.save(Path("site_dir/index"), compress=True)
loaded_index = BM25Index.load(Path("site_dir/index.json.gz"))

# Basic search
results = index.search("query terms", top_k=10)
```

### SearchEngine

```python
from doc_search.search import SearchEngine, EnhancedSearchEngine

# Load from index file
engine = SearchEngine.load(Path("site_dir/index.json.gz"))

# Search with phrase support and highlighting
results = engine.search(
    query='python "list comprehension"',
    top_k=10,
    highlight=True,
    snippet_length=150
)

for r in results:
    print(f"{r['title']} - {r['url']}")
    print(f"  Score: {r['score']:.4f}")
    print(f"  {r['snippet']}")
```

### EnhancedSearchEngine

```python
from doc_search.search import EnhancedSearchEngine

# Load with enhanced features
engine = EnhancedSearchEngine.load(
    Path("site_dir/index.json.gz"),
    enable_spellcheck=True,
    enable_autocomplete=True,
    enable_facets=True,
    enable_synonyms=False
)

# Search with all features
response = engine.search_enhanced(
    query="pyhton tutorial",  # intentional typo
    top_k=10
)

print(f"Results: {len(response['results'])}")
if response.get('suggestion'):
    print(f"Did you mean: {response['suggestion']}")

# Autocomplete
suggestions = engine.get_suggestions("pyth", max_suggestions=5)
print(f"Autocomplete: {suggestions}")
```

## Notes

- All examples use relative imports assuming you run from the repo root
- For production use, install the package with `pip install .`
- Examples create data in `~/.doc_search/sites/` by default
- Use `--help` with CLI commands to see all available options
