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
--user admin         # HTTP Basic Auth username
```

### Search Options

```bash
--limit 20           # Number of results (default: 10)
--json               # Output as JSON
--synonyms           # Enable synonym expansion
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
