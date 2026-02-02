# Operator Guide

A simple guide to using doc-search for crawling and searching documentation sites.

## Prerequisites

- Python 3.6 or higher
- No additional dependencies required (pure standard library)

## Installation

Clone the repository:

```bash
git clone https://github.com/AlanConstantino/doc-search.git
cd doc-search
```

That's it — no `pip install` needed.

## Basic Workflow

The typical workflow is: **Crawl → Index → Search**

### Step 1: Crawl a Documentation Site

```bash
python -m doc_search crawl https://docs.example.com
```

This downloads all pages from the site and stores them locally.

**Common options:**

| Option | Description | Example |
|--------|-------------|---------|
| `--max-pages N` | Limit total pages crawled | `--max-pages 500` |
| `--max-depth N` | Limit link-following depth | `--max-depth 3` |
| `--delay N` | Seconds between requests | `--delay 2.0` |
| `--workers N` | Parallel crawlers | `--workers 4` |
| `--extract-docs` | Also extract text from PDFs | `--extract-docs` |

**Example with options:**

```bash
python -m doc_search crawl https://docs.python.org \
    --max-pages 1000 \
    --delay 1.5 \
    --extract-docs
```

### Step 2: Build the Search Index

```bash
python -m doc_search index https://docs.example.com
```

This creates a BM25 search index from the crawled pages.

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--k1 N` | BM25 term frequency weight | 1.5 |
| `--b N` | BM25 document length normalization | 0.75 |
| `--no-compress` | Save uncompressed index | Compressed |
| `--no-stemming` | Disable word stemming | Stemming on |

### Step 3: Search

**Command line search:**

```bash
python -m doc_search search https://docs.example.com "your query"
```

**Interactive mode:**

```bash
python -m doc_search interactive https://docs.example.com
```

**Web interface (recommended):**

```bash
python -m doc_search serve https://docs.example.com --open
```

This opens a browser with a search interface at `http://localhost:8080`.

## Quick Reference

### All Commands

```bash
# Crawl a site
python -m doc_search crawl <url>

# Build index
python -m doc_search index <url>

# Search (CLI)
python -m doc_search search <url> "query"

# Interactive search
python -m doc_search interactive <url>

# Web UI
python -m doc_search serve <url>

# View statistics
python -m doc_search stats <url>

# List all crawled sites
python -m doc_search list

# Autocomplete suggestions
python -m doc_search autocomplete <url> "prefix"
```

### Search Tips

- **Phrase search:** Use quotes for exact phrases: `"exact phrase"`
- **Multiple terms:** Space-separated terms are AND'd together
- **Synonyms:** Add `--synonyms` to expand queries (e.g., "quick" also matches "fast")

### Common Workflows

**Quick test of a new site:**

```bash
# Crawl just 100 pages to test
python -m doc_search crawl https://docs.example.com --max-pages 100
python -m doc_search index https://docs.example.com
python -m doc_search serve https://docs.example.com --open
```

**Full crawl with PDFs:**

```bash
python -m doc_search crawl https://docs.example.com --extract-docs
python -m doc_search index https://docs.example.com
python -m doc_search serve https://docs.example.com --open
```

**Resume an interrupted crawl:**

```bash
# Just run crawl again — it automatically resumes
python -m doc_search crawl https://docs.example.com
```

**Fresh crawl (ignore previous data):**

```bash
python -m doc_search crawl https://docs.example.com --fresh
```

## Data Location

All data is stored in `~/.doc_search/sites/`:

```
~/.doc_search/sites/<site-hash>/
├── pages/           # Crawled HTML/text content
├── index.json.gz    # Compressed search index
├── metadata.json    # Site info and crawl stats
└── crawl_state.json # Resume state for interrupted crawls
```

## Troubleshooting

### "No index found"

You need to build the index before searching:

```bash
python -m doc_search index https://docs.example.com
```

### "No pages found"

The site hasn't been crawled yet:

```bash
python -m doc_search crawl https://docs.example.com
```

### Crawl is very slow

Increase parallelism (be respectful of the server):

```bash
python -m doc_search crawl https://docs.example.com --workers 4 --delay 0.5
```

### Search returns no results

1. Check that pages were crawled: `python -m doc_search stats <url>`
2. Check that index was built: Look for `index.json.gz` in the data directory
3. Try simpler queries — the search is literal, not fuzzy

### Authentication required

For sites behind HTTP Basic Auth:

```bash
python -m doc_search crawl https://docs.example.com --user admin --password secret
```

Or with a pre-encoded token:

```bash
python -m doc_search crawl https://docs.example.com --token "base64-encoded-credentials"
```

## Performance Expectations

| Metric | Typical Value |
|--------|---------------|
| Crawl speed | 30-60 pages/min (with 1s delay) |
| Index build time | 5-10 min for 15K pages |
| Search latency | <100ms |
| Storage | ~100-200MB for 15K pages |
| Memory (indexing) | ~500MB for 15K pages |
| Memory (searching) | ~50-100MB for 15K pages |

## Getting Help

```bash
# General help
python -m doc_search --help

# Command-specific help
python -m doc_search crawl --help
python -m doc_search search --help
```
