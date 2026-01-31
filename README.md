# doc-search

A self-contained Python application for searching through large technical documentation websites (5,000-15,000 pages).

**Zero dependencies** - Uses only Python 3.9+ standard library.

## ✨ What's New in v1.7.0

- 🌐 **Domain-Agnostic Facets** - Faceted search now works with any documentation site (Python, Docusaurus, ReadTheDocs, etc.) by extracting categories from URL paths
- 🔇 **Opt-in Synonyms** - Synonym expansion now disabled by default to improve precision; use `--synonyms` flag or `--synonyms-file` for custom groups
- 📄 **Pagination** - Web UI paginates results (10 per page, up to 100 results) with pure HTML navigation

### Previous Updates
- **v1.6.0**: Spell check ("Did you mean..."), Autocomplete, Faceted Search, Synonym Expansion, Porter Stemming
- **v1.4.0**: Porter Stemming, Beautiful Web UI, Colorful CLI, Performance Metrics
- **v1.3.0**: Web UI server (`serve` command)
- **v1.2.0**: Phrase search, snippet highlighting, parallel crawling

## Features

### Core
- 🕷️ **Web Crawler** - BFS crawler with politeness delays and robots.txt compliance
- ⚡ **Parallel Crawling** - Optional multi-threaded crawling with `--workers N`
- 🔐 **HTTP Basic Auth** - Support for password-protected documentation
- 📄 **HTML Text Extraction** - Smart extraction that filters navigation/boilerplate
- 🔍 **BM25 Search** - Industry-standard ranking algorithm (same as Elasticsearch)
- 📝 **Phrase Search** - Support for `"exact phrase"` queries in quotes
- ✨ **Highlighted Snippets** - Query terms are highlighted in search results
- 📍 **Smart Snippets** - Shows most relevant section with highest term density
- 💾 **Resumable Crawls** - Interrupt and resume large crawls anytime
- 🗜️ **Compressed Index** - gzip compression for efficient storage

### Enhanced Search (v1.6+)
- 💡 **Spell Correction** - "Did you mean..." suggestions for misspelled queries
- ⌨️ **Autocomplete** - Fast prefix-based term suggestions
- 🏷️ **Faceted Search** - Filter by URL path category (auto-extracted, domain-agnostic)
- 🔗 **Query Expansion** - Optional synonym matching (disabled by default, use `--synonyms` or custom file)
- 🌿 **Porter Stemming** - Word variant matching (searches→search, running→run)

### Interface
- 🖥️ **CLI Interface** - Beautiful command-line interface with interactive mode
- 🌐 **Web UI** - Beautiful search interface (pure HTML/CSS, no JavaScript)
- 📄 **Pagination** - Results paginated in web UI (10 per page, up to 100 results)

## Installation

No installation required! Just clone and run:

```bash
git clone https://github.com/AlanConstantino/doc-search.git
cd doc-search
python -m doc_search --help
```

Or copy the `doc_search/` directory to your project.

## Quick Start

### 1. Crawl a Documentation Site

```bash
# Basic crawl (single-threaded, most polite)
python -m doc_search crawl https://docs.example.com

# Parallel crawling - 4 workers (still respects per-domain rate limits)
python -m doc_search crawl https://docs.example.com --workers 4

# Crawl with authentication
python -m doc_search crawl https://docs.example.com --user admin
# (will prompt for password)

# Crawl with custom delay (be polite!)
python -m doc_search crawl https://docs.example.com --delay 2.0

# Limit pages for testing
python -m doc_search crawl https://docs.example.com --max-pages 100
```

### 2. Build the Search Index

```bash
# Index crawled pages
python -m doc_search index ~/.doc_search/sites/<site-hash>

# Or use the original URL (auto-finds the directory)
python -m doc_search index https://docs.example.com
```

### 3. Search

#### Command Line

```bash
# Single query (with colored output and performance metrics)
python -m doc_search search https://docs.example.com "api authentication"

# ✓ Found 15 results in 42.3ms
# 
# 1. Authentication API — Example Docs
#    https://docs.example.com/api/auth
#    Learn how to authenticate your API requests...

# Exact phrase search - words must appear adjacent
python -m doc_search search https://docs.example.com '"list comprehension"'

# Mix phrases with regular terms
python -m doc_search search https://docs.example.com 'python "list comprehension" tutorial'

# Show BM25 scores
python -m doc_search search https://docs.example.com "api authentication" --scores

# Output as JSON (includes timing data)
python -m doc_search search https://docs.example.com "api authentication" --json

# Disable colors (for piping/scripting)
python -m doc_search search https://docs.example.com "api" --no-color

# Interactive mode
python -m doc_search interactive https://docs.example.com
```

#### Web UI 🆕

```bash
# Start the web search interface
python -m doc_search serve https://docs.example.com

# Custom port
python -m doc_search serve https://docs.example.com --port 3000

# Open browser automatically
python -m doc_search serve https://docs.example.com --open
```

Then visit http://127.0.0.1:8080 in your browser:

- **Clean search form** - type query, hit Enter or click Search
- **Highlighted matches** in result snippets
- **Relevance scores** shown for each result  
- **Performance timing** displayed on every search
- **Beautiful dark theme** with pure CSS styling

## Commands

| Command | Description |
|---------|-------------|
| `crawl <url>` | Crawl a documentation site |
| `index <site>` | Build search index from crawled pages |
| `search <site> <query>` | Search the index (with spell check & synonyms) |
| `autocomplete <site> <prefix>` | **🆕** Get type-ahead suggestions |
| `interactive <site>` | Interactive search mode |
| `serve <site>` | Start web UI server |
| `stats <site>` | Show site statistics |
| `list` | List all crawled sites |

## Command Options

### `crawl`

| Option | Description | Default |
|--------|-------------|---------|
| `--user`, `-u` | Username for HTTP Basic Auth | - |
| `--password`, `-p` | Password (prompts if not given) | - |
| `--delay`, `-d` | Delay between requests (seconds) | 1.0 |
| `--timeout`, `-t` | Request timeout (seconds) | 30 |
| `--max-pages`, `-m` | Maximum pages to crawl | unlimited |
| `--max-depth` | Maximum link depth from start URL | unlimited |
| `--workers`, `-w` | Parallel workers (respects per-domain rate limits) | 1 |
| `--no-same-path` | Allow crawling outside the starting path | false |
| `--fresh`, `-f` | Ignore saved state, start fresh | false |
| `--quiet`, `-q` | Suppress progress output | false |

### `index`

| Option | Description | Default |
|--------|-------------|---------|
| `--k1` | BM25 k1 parameter | 1.5 |
| `--b` | BM25 b parameter | 0.75 |
| `--no-compress` | Don't compress index | false |
| `--quiet`, `-q` | Suppress progress output | false |

### `search`

| Option | Description | Default |
|--------|-------------|---------|
| `--limit`, `-l` | Number of results | 10 |
| `--scores`, `-s` | Show BM25 scores | false |
| `--json`, `-j` | Output as JSON (includes timing) | false |
| `--no-color` | Disable colored output | false |
| `--quiet`, `-q` | Suppress loading messages | false |
| `--basic` | Disable enhanced features | false |
| `--synonyms` | Enable synonym expansion (built-in programming terms) | false |
| `--synonyms-file FILE` | Load custom synonyms from JSON file | - |
| `--no-facets` | Disable faceted search | false |
| `--show-facets` | Show facet counts in output | false |
| `--filter-category CAT` | Filter by URL path category | - |
| `--filter-section SECTION` | Filter by section | - |

### `autocomplete` 🆕

| Option | Description | Default |
|--------|-------------|---------|
| `--limit`, `-l` | Maximum suggestions | 10 |
| `--json`, `-j` | Output as JSON | false |

### `serve` 🆕

| Option | Description | Default |
|--------|-------------|---------|
| `--port`, `-p` | Port to listen on | 8080 |
| `--host` | Host to bind to | 127.0.0.1 |
| `--open`, `-o` | Open browser automatically | false |

## Data Storage

All data is stored in `~/.doc_search/sites/<site-hash>/`:

```
~/.doc_search/sites/abc123def456/
├── crawl_state.json   # Resumable crawl state
├── pages/             # Cached page content
│   ├── a1b2c3d4.json
│   └── ...
├── index.json.gz      # Compressed search index
└── metadata.json      # Site info, crawl stats
```

## How It Works

### Crawling

1. **BFS Traversal** - Crawls pages breadth-first starting from the base URL
2. **Politeness** - Respects `robots.txt` and maintains configurable delays
3. **Link Extraction** - Finds all links on each page, stays on same domain
4. **Content Extraction** - Removes scripts, styles, navigation to get clean text
5. **Checkpointing** - Saves state every 100 pages for resumability

### Indexing

Uses **BM25 (Best Match 25)** ranking algorithm:

- Industry standard (used by Elasticsearch, Lucene)
- Handles term frequency saturation
- Length normalization for varying document sizes
- Configurable k1 and b parameters

### Search

1. Query tokenization (lowercase, stopword removal)
2. BM25 score calculation for matching documents
3. Results ranked by relevance score
4. Performance timing displayed for every search

## Web UI Features 🆕

The web interface provides a clean, fast search experience with **zero JavaScript**:

- **Server-side rendering** - All HTML generated on the server
- **Form-based search** - Traditional GET request, works everywhere
- **Highlighted matches** - Search terms highlighted in snippets
- **Score display** - See BM25 relevance scores for each result
- **Performance metrics** - "Found X results in Y ms" on every search
- **Beautiful dark theme** - Modern styling with pure CSS
- **Index stats** - Document count and term count in footer
- **No dependencies** - Just Python's built-in http.server

## Performance

Tested capabilities:
- **Crawl rate**: ~30-60 pages/minute (with 1s delay)
- **15,000 pages**: 4-8 hours crawl time
- **Index build**: ~5-10 minutes for 15K pages
- **Search latency**: <100ms for typical queries
- **Storage**: ~100-200MB total (pages + index)

## Examples

### Crawl Python Documentation

```bash
python -m doc_search crawl https://docs.python.org/3/
python -m doc_search index https://docs.python.org/3/
python -m doc_search search https://docs.python.org/3/ "async await"

# Or use the web UI
python -m doc_search serve https://docs.python.org/3/ --open
```

### Crawl with Auth

```bash
# For sites requiring HTTP Basic Auth
python -m doc_search crawl https://internal-docs.company.com \
    --user myusername \
    --delay 2.0

# Password will be prompted securely
```

### Resume Interrupted Crawl

```bash
# Start a crawl (Ctrl+C to interrupt)
python -m doc_search crawl https://large-docs.example.com

# Later, resume from where it left off
python -m doc_search crawl https://large-docs.example.com
```

### Check Crawl Status

```bash
python -m doc_search stats https://docs.example.com
```

Output:
```
Site: https://docs.example.com

Crawl Statistics:
  Pages crawled: 5432
  Pages failed: 12
  Data downloaded: 45.6 MB
  Time elapsed: 2.3h

Stored Pages: 5432 (52.1 MB)

Index Statistics:
  Documents: 5420
  Unique terms: 48521
  Avg document length: 342.5 terms
  BM25 k1=1.5, b=0.75
  Index size: 12.3 MB
```

## Programmatic Usage

```python
from doc_search.crawler import Crawler
from doc_search.indexer import BM25Index
from doc_search.searcher import SearchEngine

# Crawl
crawler = Crawler(
    base_url='https://docs.example.com',
    data_dir='/path/to/data',
    delay=1.0,
    auth=('username', 'password')  # Optional
)
crawler.crawl()

# Index
index = BM25Index()
index.build_from_pages('/path/to/data/pages')
index.save('/path/to/data/index')

# Search
engine = SearchEngine.load('/path/to/data/index')
results = engine.search('api authentication', top_k=10)
for r in results:
    print(f"{r['title']}: {r['url']} (score: {r['score']})")
```

## Limitations

- **English tokenization only** - No CJK or other language support
- **In-memory index** - Index loaded into RAM during search (~10-50MB for 15K pages). Fine for small-medium sites, not suitable for millions of pages
- **No JavaScript rendering** - Crawler fetches raw HTML only. SPAs and dynamically-loaded content won't be indexed
- **Keyword search only** - No semantic/vector search. Relies on BM25 + synonyms for relevance

### Data Persistence

All data is stored on disk and persists between sessions:
- **Crawled pages**: `~/.doc_search/sites/<hash>/pages/*.json`
- **Search index**: `~/.doc_search/sites/<hash>/index.json.gz`

You don't need to re-crawl to search - the index is loaded from disk each time.

## License

MIT License - see LICENSE file.

## Contributing

Contributions welcome! Please open an issue or PR.
