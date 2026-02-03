# doc-search

Search through large technical documentation websites offline.

Built for sites with 5,000–15,000+ pages. Crawl once, search instantly.

**Zero dependencies** — Pure Python 3.6+ standard library (PDF support included via vendored PyPDF2).

## Why?

Documentation sites are great, but:
- Site search is often slow or limited
- You need internet access
- No way to search across your own crawled content

doc-search solves this by crawling documentation sites and building a local search index using BM25 (the same algorithm used by Elasticsearch).

## Features

- 🕷️ **Smart Crawler** — Respects robots.txt, handles rate limits, resumes interrupted crawls
- 🔍 **BM25 Search** — Industry-standard relevance ranking
- 📄 **PDF Extraction** — Index PDF documents alongside HTML pages
- 📝 **Phrase Search** — Use `"exact phrases"` in quotes
- 💡 **Spell Check** — "Did you mean..." suggestions
- ⌨️ **Autocomplete** — Type-ahead suggestions
- 🏷️ **Faceted Search** — Filter by URL path categories
- 🌐 **Web UI** — Beautiful search interface (no JavaScript required)
- 🖥️ **CLI** — Colorful command-line interface with interactive mode

## Quick Start

### 1. Crawl a Site

```bash
python -m doc_search crawl https://docs.example.com

# Limit pages for testing
python -m doc_search crawl https://docs.example.com --max-pages 100
```

### 2. Build the Index

```bash
python -m doc_search index https://docs.example.com
```

### 3. Search

```bash
# Command line
python -m doc_search search https://docs.example.com "your query"

# Exact phrase
python -m doc_search search https://docs.example.com '"exact phrase"'

# Interactive mode
python -m doc_search interactive https://docs.example.com

# Web UI
python -m doc_search serve https://docs.example.com --open
```

## Web UI

The easiest way to search is through the built-in web interface:

```bash
# Start the server (opens browser automatically)
python -m doc_search serve https://docs.example.com --open

# Or specify a port
python -m doc_search serve https://docs.example.com --port 3000

# Using the script
./scripts/serve.sh https://docs.example.com
```

This starts a local web server at `http://localhost:8080` with:
- Search box with instant results
- Highlighted matching terms
- Click-through links to original pages
- No JavaScript required (works everywhere)

Press `Ctrl+C` to stop the server.

## Commands

| Command | Description |
|---------|-------------|
| `crawl <url>` | Crawl a documentation site |
| `index <url>` | Build search index |
| `search <url> <query>` | Search from command line |
| `interactive <url>` | Interactive search mode |
| `serve <url>` | Start web UI |
| `stats <url>` | Show crawl/index statistics |
| `list` | List all crawled sites |
| `autocomplete <url> <prefix>` | Get type-ahead suggestions |

## Common Options

### Crawl Options

```bash
--max-pages 500      # Limit number of pages
--max-depth 5        # Limit link depth
--delay 2.0          # Seconds between requests (default: 1.0)
--workers 4          # Parallel crawlers (default: 1)
--extract-docs       # Extract text from PDFs
--parser dom         # HTML parser: dom (default) or stream
--no-save-html       # Don't save raw HTML (saves disk space)
--user admin         # HTTP Basic Auth username
```

### Search Options

```bash
--limit 20           # Number of results (default: 10)
--json               # Output as JSON
--synonyms           # Enable synonym expansion
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DOC_SEARCH_NO_EMOJI` | Set to `1`, `true`, or `yes` to use ASCII fallbacks instead of emoji (for systems without emoji fonts) |

Example:
```bash
export DOC_SEARCH_NO_EMOJI=1
python -m doc_search serve ~/.doc_search/sites/*/
```

## HTML Parsers

doc-search includes two HTML parsers for text extraction:

### DOM Parser (Default)

The DOM parser builds a tree structure from HTML, enabling:
- **Smart content detection** — Finds `<main>`, `<article>`, or the best content `<div>`
- **Better boilerplate removal** — Strips nav, sidebar, footer by tag, ARIA role, and CSS class
- **Structure-aware extraction** — Understands document hierarchy

```bash
# Uses DOM parser by default
python -m doc_search crawl https://docs.example.com
python -m doc_search index https://docs.example.com
```

### Streaming Parser (Legacy)

The streaming parser processes HTML sequentially without building a tree:
- **Faster** — Lower memory usage
- **Simpler** — Basic tag filtering

```bash
# Use streaming parser
python -m doc_search crawl https://docs.example.com --parser=stream
python -m doc_search index https://docs.example.com --parser=stream
```

### Re-indexing with a Different Parser

If raw HTML was saved during crawling (default), you can re-index with a different parser without re-crawling:

```bash
# Re-index existing crawl with DOM parser
python -m doc_search index https://docs.example.com --parser=dom
```

## PDF Extraction

Extract and index text from PDF documents alongside HTML pages:

```bash
python -m doc_search crawl https://docs.example.com --extract-docs
```

PDFs are indexed with the same format as HTML pages, so they appear in search results seamlessly. Metadata (title, author, page count) is extracted when available.

**Note:** Encrypted PDFs require the optional `cryptography` package. Image-only PDFs (scanned documents) won't have extractable text.

## Data Storage

All data is stored in `~/.doc_search/sites/`:

```
~/.doc_search/sites/<site-hash>/
├── pages/           # Crawled page content
├── index.json.gz    # Search index
└── metadata.json    # Site info
```

## SSL Certificate Verification

doc-search **disables SSL certificate verification by default** when crawling sites.

### Why?

Many documentation sites — especially internal company wikis, staging environments, or self-hosted tools — use self-signed certificates. Requiring valid certificates would make doc-search unusable for these common scenarios.

### Security Implications

With SSL verification disabled:
- Connections are still encrypted (HTTPS)
- The server's identity is **not verified**
- Man-in-the-middle attacks become theoretically possible

### When This Matters

**Low risk scenarios (typical doc-search usage):**
- Crawling public documentation sites
- Crawling internal sites on trusted networks
- One-time crawls for building a local index

**Higher risk scenarios:**
- Crawling over untrusted networks (public WiFi)
- Sites requiring authentication (credentials could be intercepted)

### Future Consideration

A `--verify-ssl` flag may be added in the future for users who need strict certificate validation. See the issue tracker if this is important for your use case.

## Documentation

| Document | Description |
|----------|-------------|
| [API Reference](docs/API.md) | Library usage guide with code examples |
| [Architecture](docs/ARCHITECTURE.md) | Data flow and module interactions |
| [Index Format](docs/INDEX_FORMAT.md) | BM25 index file specification |
| [Operator Guide](docs/OPERATOR_GUIDE.md) | Workflow guide and troubleshooting |
| [Examples](examples/) | Runnable usage examples |

## Using as a Library

```python
from doc_search.crawler import Crawler
from doc_search.indexer import BM25Index
from doc_search.searcher import EnhancedSearchEngine

# Crawl
crawler = Crawler(base_url='https://docs.example.com', data_dir='./data')
crawler.crawl()

# Index
index = BM25Index()
index.build_from_pages('./data/pages')

# Search
engine = EnhancedSearchEngine(index, pages_dir='./data/pages')
results = engine.search('your query')
```

See [docs/API.md](docs/API.md) for comprehensive library documentation.

## Development

```bash
# Run tests (955 tests)
python -m pytest

# Run specific test file
python -m pytest tests/test_crawler.py
```

## Limitations

- **English only** — Tokenization assumes space-separated words
- **In-memory index** — Index loads into RAM (~10-50MB for 15K pages)
- **Static HTML only** — No JavaScript rendering (SPAs won't work)

## Performance

| Metric | Typical Value |
|--------|---------------|
| Crawl speed | 30-60 pages/min (1s delay) |
| Index build | 5-10 min for 15K pages |
| Search latency | <100ms |
| Storage | ~100-200MB for 15K pages |

## License

MIT
