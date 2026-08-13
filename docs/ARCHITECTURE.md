# Architecture Overview

This document describes the high-level architecture of doc-search, explaining how the modules fit together and how data flows through the system.

## System Overview

doc-search is a command-line tool for building and searching local indexes of documentation websites. It follows a three-stage pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              doc-search                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   1. CRAWL                    2. INDEX                    3. SEARCH         │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐       │
│  │   Website   │  ────▶    │   Pages/    │  ────▶    │   Search    │       │
│  │   Crawler   │           │   Index     │           │   Engine    │       │
│  └─────────────┘           └─────────────┘           └─────────────┘       │
│        │                         │                         │               │
│        ▼                         ▼                         ▼               │
│  ~/.doc_search/            index.json.gz              CLI / Web UI         │
│   sites/<hash>/                                                            │
│    pages/*.json                                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Module Organization

Packages are layered. **Dependencies only point down.** `app` may import anything below it; `core` imports nothing above it.

```
doc_search/
├── __init__.py              # version
├── __main__.py              # python -m doc_search → app.cli.main
│
├── core/                    # foundation (no upward imports)
│   ├── constants.py         # tunables (BM25/rerank/crawl)
│   ├── config.py            # sites_dir / JSON config
│   ├── paths.py             # PACKAGE_ROOT, REPO_ROOT, VENDOR_DIR
│   ├── http.py              # SSL context, Basic Auth header
│   ├── urls.py              # normalize_url, site_hash, …
│   ├── text.py              # tokenize, STOP_WORDS, format_size
│   ├── stemmer.py           # Porter stemmer
│   └── data/                # bundled colors.json, synonyms.json
│
├── extract/                 # HTML + document extractors (→ core)
│   ├── html.py              # streaming HTML parser
│   ├── dom.py               # DOM parser / boilerplate strip
│   ├── pdf.py / word.py / excel.py / pptx.py
│   └── registry.py          # ExtractorRegistry — crawl never names PDFExtractor
│
├── crawl/                   # fetch / filter / persist (→ extract, core)
│   ├── crawler.py           # orchestrator
│   ├── fetcher.py, url_filter.py, processor.py
│   ├── state.py, robots.py, rate_limiter.py
│
├── index/                   # BM25 store only (→ extract, core)
│   └── store.py             # BM25Index, find_index_path
│
├── search/                  # engines + optional features (→ index, core)
│   ├── engine.py            # SearchEngine, EnhancedSearchEngine
│   ├── snippets.py          # highlight / snippet extract (no ANSI)
│   ├── multi.py             # MultiSiteSearchEngine
│   └── features/            # spellcheck, synonyms, ngram, facets,
│                            # suggester, reranker, clicks, side_indexes
│
└── app/                     # CLI + web UI (→ search / crawl / index)
    ├── terminal.py          # ANSI colors / emoji (CLI only)
    ├── server.py            # HTTP UI
    ├── static/              # styles.css, search.js
    └── cli/
        ├── __init__.py      # main()
        ├── parsers.py
        ├── formatters.py    # format_results (ANSI)
        └── commands.py      # cmd_* implementations
```

Compatibility shims at the old import paths (`doc_search.utils`, `doc_search.searcher`,
`doc_search.crawler`, …) re-export the new locations so existing scripts keep working.

## Data Flow

### Stage 1: Crawling

```
                                    ┌──────────────┐
                                    │   Website    │
                                    └──────┬───────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────┐
│                         Crawler                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │
│  │ RateLimiter │    │ RobotsCheck │    │ HTMLTextExtractor       │ │
│  │             │    │             │    │ PDFExtractor (optional) │ │
│  └─────────────┘    └─────────────┘    └─────────────────────────┘ │
│                            │                                        │
│                            ▼                                        │
│                     ┌─────────────┐                                │
│                     │ CrawlState  │──────▶ state.json              │
│                     └─────────────┘                                │
└────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
                              ~/.doc_search/sites/<hash>/pages/
                                  ├── <url_hash>.json
                                  ├── <url_hash>.json
                                  └── ...
```

**Key Components:**
- **Crawler** (`crawl/crawler.py`): Orchestrates the crawl, manages URL queue
- **CrawlState** (`crawl/state.py`): Tracks visited URLs, enables resume
- **RateLimiter** (`crawl/rate_limiter.py`): Enforces delays between requests
- **RobotsChecker** (`crawl/robots.py`): Respects robots.txt rules
- **HTMLTextExtractor** (`extract/html.py`): Extracts text from HTML
- **PDFExtractor** (`extract/pdf.py`): Extracts text from PDFs

### Stage 2: Indexing

```
              pages/*.json
                   │
                   ▼
┌────────────────────────────────────────────────────────────────────┐
│                         Indexer                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐ │
│  │  tokenize() │    │   stem()    │    │   BM25Index             │ │
│  │  (utils.py) │    │ (stemmer.py)│    │   - inverted index      │ │
│  │             │    │             │    │   - document lengths    │ │
│  │  - lowercase│    │  - Porter   │    │   - term frequencies    │ │
│  │  - stopwords│    │    stemming │    │   - average doc length  │ │
│  └─────────────┘    └─────────────┘    └─────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
                              ~/.doc_search/sites/<hash>/
                                  └── index.json.gz
```

**Key Components:**
- **BM25Index** (`index/store.py`): Builds inverted index with BM25 statistics
- **tokenize()** (`core/text.py` / `core/urls.py`): Splits text into searchable tokens
- **stem()** (`core/stemmer.py`): Reduces words to root forms

### Stage 3: Searching

```
                     User Query
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│                      SearchEngine                                   │
│                                                                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│  │  tokenize() │    │   BM25      │    │  Spellcheck │            │
│  │             │───▶│   Scoring   │    │  Suggestions│            │
│  └─────────────┘    └─────────────┘    └─────────────┘            │
│        │                  │                   │                    │
│        │                  │                   │                    │
│        ▼                  ▼                   ▼                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│  │  Synonyms   │    │   Facets    │    │ Autocomplete│            │
│  │  Expansion  │    │  Filtering  │    │             │            │
│  └─────────────┘    └─────────────┘    └─────────────┘            │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              searcher_utils.py                               │  │
│  │  - find_best_snippet()   - highlight_terms()                │  │
│  │  - format_results()      - highlight_terms_ansi()           │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │    CLI / Web UI       │
              │  ┌─────────────────┐  │
              │  │    server.py    │  │
              │  │  (HTTP server)  │  │
              │  └─────────────────┘  │
              └───────────────────────┘
```

**Key Components:**
- **SearchEngine** (`search/engine.py`): Query processing and result ranking
- **SpellChecker** (`search/features/spellcheck.py`): "Did you mean..." suggestions
- **Autocomplete** (`search/features/suggester.py`): Content-based type-ahead
- **Facets** (`search/features/facets.py`): URL path categorization
- **Synonyms** (`search/features/synonyms.py`): Query expansion
- **searcher_utils** (`search/snippets.py`): Result formatting

## Module Dependencies

Hard rule: **arrows only point down.**

```
                         ┌─────────────┐
                         │    core     │
                         │ constants   │
                         │ config urls │
                         │ text/http   │
                         └──────┬──────┘
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              │
          ┌────────────┐  ┌──────────┐         │
          │  extract   │  │  (used   │         │
          │ html/pdf/… │  │   by     │         │
          │ registry   │  │  all)    │         │
          └─────┬──────┘  └──────────┘         │
                │                              │
        ┌───────┴────────┐                     │
        ▼                ▼                     │
 ┌────────────┐   ┌────────────┐               │
 │   crawl    │   │   index    │◄──────────────┘
 │  crawler   │   │ BM25Index  │
 └────────────┘   └─────┬──────┘
                        │
                        ▼
                 ┌────────────┐
                 │   search   │
                 │ engine +   │
                 │ features/  │
                 └─────┬──────┘
                       │
                       ▼
                 ┌────────────┐
                 │    app     │
                 │  cli/      │
                 │  server    │
                 │  terminal  │
                 └────────────┘
```

There is **no** `commands ↔ multi_search` cycle: multi-site search lives in
`search.multi` and resolves `sites_dir` via `core.config`. CLI commands import
it; it does not import CLI.

Sidecar indexes (SymSpell / n-gram) are built by `search.features.side_indexes`,
not by `BM25Index`, so the index layer never imports search.

## Storage Layout

The sites root defaults to `~/.doc_search/sites/` and is configurable via
top-level `doc_search.json` (`sites_dir`) or `DOC_SEARCH_SITES_DIR`
(see `doc_search.config.get_sites_dir`).

```
~/.doc_search/
└── sites/
    └── <site-hash>/                  # 12-char hash of domain
        ├── pages/                    # Crawled content
        │   ├── <url-hash>.json       # Page content + metadata
        │   ├── <url-hash>.json
        │   └── ...
        ├── index.json.gz             # Compressed BM25 index
        ├── metadata.json             # Site info (URL, crawl date)
        └── state.json                # Crawl state (for resume)
```

**Page JSON format:**
```json
{
  "url": "https://docs.example.com/page",
  "title": "Page Title",
  "text": "Extracted text content...",
  "headings": [[1, "Main Heading"], [2, "Subheading"]],
  "fetched_at": "2024-02-01T12:00:00"
}
```

## Key Design Decisions

### Pure Python / No Dependencies
The entire codebase uses only Python 3.6+ standard library (except PyPDF2 which is vendored). This ensures:
- Easy installation (`pip install` not required)
- No version conflicts
- Predictable behavior

### In-Memory Index
The search index loads entirely into RAM. This provides:
- Sub-100ms search latency
- Simple implementation
- Trade-off: ~10-50MB memory for 15K pages

### BM25 Ranking
BM25 (Okapi BM25) is used for relevance scoring because:
- Industry standard (Elasticsearch, Lucene default)
- Handles document length normalization
- Tunable parameters (k1, b)

### Incremental Crawling
Crawl state persists to disk, enabling:
- Resume after interruption
- Incremental updates (re-check changed pages)
- Checkpoint every 100 pages

## Configuration

All magic numbers are centralized in `constants.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `DEFAULT_CRAWL_DELAY` | 1.0s | Delay between requests |
| `CHECKPOINT_INTERVAL` | 100 | Pages between state saves |
| `DEFAULT_SNIPPET_LENGTH` | 150 | Search result snippet length |
| BM25 `k1`/`b` | 1.5 / 0.75 | Set on `BM25Index` (not constants.py) |

## Detailed Data Flow

This section documents how data flows through each pipeline stage, showing the transformations and module interactions at each step.

### Crawl Pipeline: URL → Fetch → Parse → Store

The crawler orchestrates a multi-step pipeline that transforms URLs into stored page content:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        CRAWL PIPELINE DETAIL                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────┐                                                                 │
│   │  Start    │ base_url (e.g., "https://docs.python.org/3/")                  │
│   └─────┬─────┘                                                                 │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  1. URL NORMALIZATION (utils.normalize_url)                          │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │  • Lowercase scheme + host                                           │      │
│   │  • Remove default ports (:80, :443)                                  │      │
│   │  • Remove fragments (#section)                                       │      │
│   │  • Sort query parameters                                             │      │
│   │  • Resolve path (/../, /./)                                          │      │
│   │                                                                       │      │
│   │  Input:  "HTTPS://Docs.Python.org:443/3/../3/library/../library/"    │      │
│   │  Output: "https://docs.python.org/3/library/"                        │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  2. CRAWL ELIGIBILITY CHECK                                          │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │      │
│   │  │ CrawlState       │  │ RobotsChecker    │  │ URL Filters      │   │      │
│   │  │ is_visited(url)  │  │ can_fetch(url)   │  │ • Extension skip │   │      │
│   │  │                  │  │                  │  │ • Path patterns  │   │      │
│   │  │ visited: Set     │  │ • User-Agent     │  │ • Domain check   │   │      │
│   │  │ pending: List    │  │ • Disallow rules │  │ • Depth limit    │   │      │
│   │  └──────────────────┘  └──────────────────┘  └──────────────────┘   │      │
│   │                                                                       │      │
│   │  Skip if: already visited OR robots disallowed OR filtered out       │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  3. RATE LIMITING (rate_limiter.RateLimiter)                         │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Per-domain tracking:                                                 │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ domain_timestamps = {                                        │    │      │
│   │  │   "docs.python.org": 1704067200.0,  # last request time     │    │      │
│   │  │   "requests.readthedocs.io": 1704067198.5                   │    │      │
│   │  │ }                                                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  wait_for_domain(domain):                                            │      │
│   │    elapsed = now - last_request_time                                 │      │
│   │    if elapsed < delay:                                               │      │
│   │        sleep(delay - elapsed)  # Respect crawl-delay                 │      │
│   │    update timestamp                                                   │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  4. HTTP FETCH (crawler._fetch)                                      │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Request headers:                                                     │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ User-Agent: DocSearchBot/1.2                                 │    │      │
│   │  │ Accept: text/html,application/xhtml+xml,...                  │    │      │
│   │  │ Accept-Encoding: gzip, deflate                               │    │      │
│   │  │ If-None-Match: "etag123"        # Incremental crawl          │    │      │
│   │  │ If-Modified-Since: "Wed, ..."   # Incremental crawl          │    │      │
│   │  │ Authorization: Basic ...        # If auth configured         │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  Response handling:                                                   │      │
│   │  • 200 OK → content, content_type, {etag, last_modified}             │      │
│   │  • 304 Not Modified → None, None, {not_modified: True}               │      │
│   │  • 429 Too Many → backoff, retry later                               │      │
│   │  • 4xx/5xx → record error, mark failed                               │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  5. CONTENT PARSING (parser.extract_text / pdf_extractor)            │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  HTML Extraction (parser.py):                                         │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Input HTML:                                                  │    │      │
│   │  │   <html><head><title>Functions</title></head>               │    │      │
│   │  │   <body><h1>Built-in Functions</h1>                         │    │      │
│   │  │   <p>The Python interpreter has...</p></body></html>        │    │      │
│   │  │                                                              │    │      │
│   │  │ Output:                                                      │    │      │
│   │  │   {                                                          │    │      │
│   │  │     "title": "Functions",                                    │    │      │
│   │  │     "description": "",                                       │    │      │
│   │  │     "text": "Built-in Functions The Python interpreter...", │    │      │
│   │  │     "headings": [[1, "Built-in Functions"]]                  │    │      │
│   │  │   }                                                          │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  PDF Extraction (pdf_extractor.py) - when --extract-docs enabled:    │      │
│   │  • Download PDF to temp file                                          │      │
│   │  • Extract text using PyPDF2 (vendored)                              │      │
│   │  • Extract title from metadata or filename                            │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  6. LINK EXTRACTION & QUEUE MANAGEMENT                               │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  extract_links(html, base_url):                                       │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Found: <a href="/3/library/functions.html">                  │    │      │
│   │  │ Resolved: https://docs.python.org/3/library/functions.html  │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  CrawlState queue management:                                         │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ pending = [                                                  │    │      │
│   │  │   ("https://docs.python.org/3/library/", 1),    # depth=1   │    │      │
│   │  │   ("https://docs.python.org/3/tutorial/", 1),               │    │      │
│   │  │   ("https://docs.python.org/3/library/os.html", 2)          │    │      │
│   │  │ ]                                                            │    │      │
│   │  │ visited = {"https://docs.python.org/3/", ...}               │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  7. PAGE STORAGE                                                     │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Filename: SHA256(url)[:16] + ".json"                                 │      │
│   │  Location: ~/.doc_search/sites/<site_hash>/pages/                    │      │
│   │                                                                       │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ {                                                            │    │      │
│   │  │   "url": "https://docs.python.org/3/library/functions.html",│    │      │
│   │  │   "title": "Built-in Functions",                             │    │      │
│   │  │   "description": "...",                                      │    │      │
│   │  │   "text": "Built-in Functions The Python interpreter...",   │    │      │
│   │  │   "headings": [[1, "Built-in Functions"], [2, "abs()"]...], │    │      │
│   │  │   "depth": 1,                                                │    │      │
│   │  │   "crawled_at": 1704067200.0,                                │    │      │
│   │  │   "etag": "\"abc123\"",           # For incremental crawl   │    │      │
│   │  │   "last_modified": "Wed, 01...",  # For incremental crawl   │    │      │
│   │  │   "content_hash": "a1b2c3..."     # SHA256 of content       │    │      │
│   │  │ }                                                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌───────────┐                                                                 │
│   │  Loop     │ Pop next URL from pending queue, repeat steps 2-7              │
│   └───────────┘                                                                 │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Parallel Crawling (when workers > 1):**

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        PARALLEL CRAWL ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────────────────────────────────────────────────────────────────┐    │
│   │                      ThreadPoolExecutor                                │    │
│   │   ┌─────────────────────────────────────────────────────────────────┐ │    │
│   │   │  Shared State (thread-safe with locks):                          │ │    │
│   │   │  • CrawlState.pending (URL queue)                               │ │    │
│   │   │  • CrawlState.visited (seen URLs)                               │ │    │
│   │   │  • RateLimiter.domain_timestamps                                │ │    │
│   │   └─────────────────────────────────────────────────────────────────┘ │    │
│   │                                                                        │    │
│   │   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │    │
│   │   │  Worker 1  │  │  Worker 2  │  │  Worker 3  │  │  Worker N  │     │    │
│   │   │ ─────────  │  │ ─────────  │  │ ─────────  │  │ ─────────  │     │    │
│   │   │ pop_url()  │  │ pop_url()  │  │ pop_url()  │  │ pop_url()  │     │    │
│   │   │ fetch()    │  │ fetch()    │  │ fetch()    │  │ fetch()    │     │    │
│   │   │ parse()    │  │ parse()    │  │ parse()    │  │ parse()    │     │    │
│   │   │ save()     │  │ save()     │  │ save()     │  │ save()     │     │    │
│   │   │ add_urls() │  │ add_urls() │  │ add_urls() │  │ add_urls() │     │    │
│   │   └────────────┘  └────────────┘  └────────────┘  └────────────┘     │    │
│   └───────────────────────────────────────────────────────────────────────┘    │
│                                                                                 │
│   Note: RateLimiter ensures politeness even with parallel workers              │
│   by tracking per-domain request timestamps.                                    │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Index Building: Pages → Tokenize → BM25 Index

> **Indexing posture (v2.5+):** The indexer treats crawl-time `text`/`title`/`headings`
> as canonical (extract ≠ index). It does **not** re-parse `raw_html` unless
> `reparse=True` / CLI `--reparse`. Section chunks and HTML link scans are off by
> default. Average document length uses a running total (O(1) per add). Content
> suggestions are built from in-memory document metadata, not a second pages walk.


The indexer transforms crawled pages into a searchable inverted index:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        INDEX BUILDING PIPELINE                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────┐                                                                 │
│   │  Input    │ ~/.doc_search/sites/<hash>/pages/*.json                        │
│   └─────┬─────┘                                                                 │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  1. LOAD PAGE DATA                                                   │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  For each *.json file in pages/:                                      │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ page = {                                                     │    │      │
│   │  │   "url": "https://docs.python.org/3/library/functions.html",│    │      │
│   │  │   "title": "Built-in Functions",                             │    │      │
│   │  │   "text": "The Python interpreter has a number of...",      │    │      │
│   │  │   "headings": [[1, "Built-in Functions"], [2, "abs()"]]     │    │      │
│   │  │ }                                                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  2. TOKENIZATION (utils.tokenize)                                    │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Step 2a: Extract words with regex [a-z][a-z0-9_]*                   │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ "Built-in Functions (v3.12)" →                              │    │      │
│   │  │   ["built", "in", "functions", "v3", "12"]                  │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  Step 2b: Remove stop words (a, the, is, are, in, of, ...)           │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ ["built", "in", "functions", "v3", "12"] →                  │    │      │
│   │  │   ["built", "functions", "v3"]   # "in", "12" removed       │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  Step 2c: Porter Stemming (stemmer.stem) - optional                  │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Stemming algorithm (5 steps):                                │    │      │
│   │  │   "functions" → "function" (step 1a: remove -s)             │    │      │
│   │  │   "running"   → "run"      (step 1b: remove -ing, fix)     │    │      │
│   │  │   "happily"   → "happili"  → "happi" (step 1c: y→i)        │    │      │
│   │  │                                                              │    │      │
│   │  │ Result: ["built", "function", "v3"]                         │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  3. WEIGHTED TOKEN AGGREGATION                                       │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Tokens are weighted by location:                                     │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Title tokens:    3× weight (repeated 3 times)               │    │      │
│   │  │ H1 headings:     3× weight                                   │    │      │
│   │  │ H2 headings:     2× weight                                   │    │      │
│   │  │ H3+ headings:    1× weight                                   │    │      │
│   │  │ Body text:       1× weight                                   │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  Example aggregation:                                                 │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ title_tokens = ["built", "function"] × 3                     │    │      │
│   │  │ heading_tokens = ["abs"] × 3 (h2 = 2×)                       │    │      │
│   │  │ text_tokens = ["python", "interpret", "number", ...]        │    │      │
│   │  │                                                              │    │      │
│   │  │ all_tokens = title + headings + text                        │    │      │
│   │  │            = ["built", "built", "built", "function", ...]   │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  4. TERM FREQUENCY CALCULATION                                       │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Count occurrences of each token in document:                         │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ term_freqs = {                                               │    │      │
│   │  │   "built": 5,      # 3 from title + 2 from body             │    │      │
│   │  │   "function": 12,  # 3 from title + 9 from body             │    │      │
│   │  │   "python": 8,                                               │    │      │
│   │  │   "interpret": 3,                                            │    │      │
│   │  │   ...                                                        │    │      │
│   │  │ }                                                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  5. INVERTED INDEX UPDATE                                            │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Update index data structures:                                        │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ # Inverted index: term → [(doc_id, term_freq), ...]         │    │      │
│   │  │ index = {                                                    │    │      │
│   │  │   "function": [(0, 12), (1, 3), (5, 8), ...],               │    │      │
│   │  │   "python": [(0, 8), (2, 15), (3, 4), ...],                 │    │      │
│   │  │   "built": [(0, 5), (7, 2), ...],                           │    │      │
│   │  │   ...                                                        │    │      │
│   │  │ }                                                            │    │      │
│   │  │                                                              │    │      │
│   │  │ # Document frequencies: term → count of docs containing it  │    │      │
│   │  │ doc_freqs = {"function": 1523, "python": 4891, ...}         │    │      │
│   │  │                                                              │    │      │
│   │  │ # Document lengths: doc_id → total token count              │    │      │
│   │  │ doc_lengths = {0: 847, 1: 234, 2: 1502, ...}                │    │      │
│   │  │                                                              │    │      │
│   │  │ # Document metadata: doc_id → {url, title, description}     │    │      │
│   │  │ documents = {                                                │    │      │
│   │  │   0: {"url": "...", "title": "Built-in Functions", ...},   │    │      │
│   │  │   1: {"url": "...", "title": "Data Types", ...},           │    │      │
│   │  │   ...                                                        │    │      │
│   │  │ }                                                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  6. STATISTICS COMPUTATION                                           │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  After all documents processed:                                       │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ total_docs = 15234                                          │    │      │
│   │  │ avg_doc_length = sum(doc_lengths) / total_docs = 523.7     │    │      │
│   │  │ unique_terms = len(index) = 48291                           │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  7. INDEX SERIALIZATION                                              │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Output: ~/.doc_search/sites/<hash>/index.json.gz                    │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ {                                                            │    │      │
│   │  │   "k1": 1.5,                    # BM25 parameter            │    │      │
│   │  │   "b": 0.75,                    # BM25 parameter            │    │      │
│   │  │   "stem": true,                 # Stemming enabled          │    │      │
│   │  │   "total_docs": 15234,                                      │    │      │
│   │  │   "avg_doc_length": 523.7,                                  │    │      │
│   │  │   "documents": {...},           # Metadata                  │    │      │
│   │  │   "url_to_id": {...},           # URL → doc_id mapping     │    │      │
│   │  │   "index": {...},               # Inverted index            │    │      │
│   │  │   "doc_lengths": {...},                                     │    │      │
│   │  │   "doc_freqs": {...}                                        │    │      │
│   │  │ }                                                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  Compressed with gzip (~10-15% of uncompressed size)                 │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Search Query Processing: Query → Tokenize → Score → Rank

The search engine processes queries and returns ranked results:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        SEARCH QUERY PIPELINE                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌───────────┐                                                                 │
│   │  Input    │ User query: "python list comprehension"                        │
│   └─────┬─────┘                                                                 │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  1. QUERY PARSING (searcher.parse_query)                             │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Supports mixed terms and exact phrases:                              │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Query: 'python "list comprehension" tutorial'               │    │      │
│   │  │                                                              │    │      │
│   │  │ Output:                                                      │    │      │
│   │  │   terms = ["python", "tutorial"]                            │    │      │
│   │  │   phrases = [["list", "comprehension"]]                     │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  2. ENHANCED FEATURES (EnhancedSearchEngine only)                    │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  2a. Spellcheck (spellcheck.SpellChecker):                           │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Query: "pythn functins"                                     │    │      │
│   │  │ Suggestion: "python functions"                              │    │      │
│   │  │                                                              │    │      │
│   │  │ Algorithm: Edit distance ≤ 2, weighted by term frequency    │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  2b. Synonym Expansion (synonyms.SynonymExpander):                   │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Query terms: ["error", "fix"]                               │    │      │
│   │  │ Expanded: ["error", "exception", "fix", "solve", "debug"]  │    │      │
│   │  │                                                              │    │      │
│   │  │ Built-in groups: {error, exception, bug}, {fix, solve}...  │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  3. QUERY TOKENIZATION                                               │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Same pipeline as indexing for consistency:                           │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ "python list comprehension" →                               │    │      │
│   │  │   lowercase → "python list comprehension"                   │    │      │
│   │  │   extract words → ["python", "list", "comprehension"]       │    │      │
│   │  │   remove stopwords → ["python", "list", "comprehension"]    │    │      │
│   │  │   stem → ["python", "list", "comprehens"]                   │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  4. CANDIDATE RETRIEVAL (Inverted Index Lookup)                      │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  For each query term, retrieve posting lists:                         │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ index["python"] → [(0, 8), (2, 15), (3, 4), (7, 22), ...]   │    │      │
│   │  │ index["list"] → [(0, 3), (1, 7), (2, 5), (8, 12), ...]      │    │      │
│   │  │ index["comprehens"] → [(0, 5), (2, 8), (15, 3), ...]        │    │      │
│   │  │                                                              │    │      │
│   │  │ Candidate docs: {0, 1, 2, 3, 7, 8, 15, ...}                 │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  5. BM25 SCORING                                                     │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  For each candidate document, calculate BM25 score:                   │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │                                                              │    │      │
│   │  │  BM25 Formula:                                               │    │      │
│   │  │  ─────────────                                               │    │      │
│   │  │                        (k1 + 1) × tf                         │    │      │
│   │  │  score = Σ  IDF(t) × ─────────────────────────────          │    │      │
│   │  │         t∈q            tf + k1 × (1 - b + b × |D|/avgdl)    │    │      │
│   │  │                                                              │    │      │
│   │  │  Where:                                                      │    │      │
│   │  │    t = query term                                            │    │      │
│   │  │    tf = term frequency in document                           │    │      │
│   │  │    |D| = document length                                     │    │      │
│   │  │    avgdl = average document length                           │    │      │
│   │  │    k1 = 1.5 (term saturation)                               │    │      │
│   │  │    b = 0.75 (length normalization)                          │    │      │
│   │  │                                                              │    │      │
│   │  │  IDF(t) = log((N - df + 0.5) / (df + 0.5) + 1)              │    │      │
│   │  │    N = total documents                                       │    │      │
│   │  │    df = documents containing term                            │    │      │
│   │  │                                                              │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  Example calculation for doc 0:                                       │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Query: "python list"                                        │    │      │
│   │  │ Doc 0: length=847, tf(python)=8, tf(list)=3                 │    │      │
│   │  │ Global: N=15234, avgdl=523.7                                │    │      │
│   │  │         df(python)=4891, df(list)=2103                      │    │      │
│   │  │                                                              │    │      │
│   │  │ IDF(python) = log((15234-4891+0.5)/(4891+0.5)+1) = 1.23    │    │      │
│   │  │ IDF(list)   = log((15234-2103+0.5)/(2103+0.5)+1) = 1.89    │    │      │
│   │  │                                                              │    │      │
│   │  │ score(python) = 1.23 × (2.5×8)/(8+1.5×(0.25+0.75×847/523.7))│    │      │
│   │  │               = 1.23 × 20 / 10.67 = 2.31                    │    │      │
│   │  │                                                              │    │      │
│   │  │ score(list) = 1.89 × (2.5×3)/(3+1.5×(0.25+0.75×847/523.7)) │    │      │
│   │  │             = 1.89 × 7.5 / 5.67 = 2.50                      │    │      │
│   │  │                                                              │    │      │
│   │  │ total_score = 2.31 + 2.50 = 4.81                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  6. PHRASE FILTERING (if exact phrases in query)                     │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  For queries with "quoted phrases":                                   │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Query: 'python "list comprehension"'                        │    │      │
│   │  │                                                              │    │      │
│   │  │ For each candidate doc with high BM25 score:                │    │      │
│   │  │   1. Load full page text from pages/<hash>.json             │    │      │
│   │  │   2. Check if phrase appears (adjacent words)               │    │      │
│   │  │   3. Filter out docs missing the phrase                     │    │      │
│   │  │                                                              │    │      │
│   │  │ check_phrase_match(text, ["list", "comprehension"]):        │    │      │
│   │  │   Pattern: \blist\W+comprehension\b                         │    │      │
│   │  │   Match in "using list comprehension syntax" ✓              │    │      │
│   │  │   No match in "list of comprehension types" ✗              │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  7. FACET FILTERING (EnhancedSearchEngine)                           │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Filter by URL path categories:                                       │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ facet_filters = {"section": "library"}                      │    │      │
│   │  │                                                              │    │      │
│   │  │ Keep only docs where URL contains /library/                 │    │      │
│   │  │   ✓ https://docs.python.org/3/library/functions.html       │    │      │
│   │  │   ✗ https://docs.python.org/3/tutorial/datastructures.html │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  8. RANKING & TOP-K SELECTION                                        │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Sort by score, take top k:                                           │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ sorted_docs = sorted(scores.items(), key=score, reverse=True)│    │      │
│   │  │ top_results = sorted_docs[:top_k]                           │    │      │
│   │  │                                                              │    │      │
│   │  │ [(doc_id=0, score=4.81),                                    │    │      │
│   │  │  (doc_id=15, score=4.52),                                   │    │      │
│   │  │  (doc_id=2, score=3.98), ...]                               │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  9. SNIPPET GENERATION (searcher_utils)                              │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  find_best_snippet(text, query_terms, phrases, length=150):          │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ 1. Find positions of all query terms in text                │    │      │
│   │  │ 2. Score windows by term density                            │    │      │
│   │  │ 3. Extract best window with context                         │    │      │
│   │  │ 4. Expand to sentence boundaries if possible                │    │      │
│   │  │                                                              │    │      │
│   │  │ Text: "Python supports list comprehension, a powerful..."   │    │      │
│   │  │ Snippet: "...supports list comprehension, a powerful..."    │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   │                                                                       │      │
│   │  highlight_terms(snippet, terms):                                     │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ Input:  "Python supports list comprehension"                │    │      │
│   │  │ Output: "<mark>Python</mark> supports <mark>list</mark>     │    │      │
│   │  │          <mark>comprehension</mark>"                         │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────┐      │
│   │  10. RESULT FORMATTING                                               │      │
│   │  ─────────────────────────────────────────────────────────────────   │      │
│   │                                                                       │      │
│   │  Final output:                                                        │      │
│   │  ┌─────────────────────────────────────────────────────────────┐    │      │
│   │  │ [                                                            │    │      │
│   │  │   {                                                          │    │      │
│   │  │     "url": "https://docs.python.org/3/tutorial/data...",    │    │      │
│   │  │     "title": "Data Structures",                              │    │      │
│   │  │     "snippet": "...<mark>list</mark> <mark>comprehension</mark>...",│    │
│   │  │     "description": "This chapter describes...",              │    │      │
│   │  │     "score": 4.81,                                           │    │      │
│   │  │     "facets": {"section": "tutorial"}  # Enhanced only      │    │      │
│   │  │   },                                                         │    │      │
│   │  │   ...                                                        │    │      │
│   │  │ ]                                                            │    │      │
│   │  └─────────────────────────────────────────────────────────────┘    │      │
│   └─────────────────────────────────────────────────────────────────────┘      │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Complete Workflow: Crawl → Index → Search

The following diagram shows the end-to-end workflow and how data transforms at each stage:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     COMPLETE DOC-SEARCH WORKFLOW                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 1: CRAWL                                                           │  │
│  │  Command: doc-search crawl https://docs.python.org/3/                     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│         │                                                                       │
│         │  Input: Base URL                                                      │
│         │                                                                       │
│         ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                           │  │
│  │   Website ──────────────────────────────────────────────────────────┐    │  │
│  │      │                                                               │    │  │
│  │      ▼                                                               │    │  │
│  │   ┌────────────┐    ┌────────────┐    ┌────────────┐                │    │  │
│  │   │ robots.txt │───▶│ RateLimiter│───▶│  Fetcher   │                │    │  │
│  │   │ compliance │    │ (1s delay) │    │  (HTTP)    │                │    │  │
│  │   └────────────┘    └────────────┘    └─────┬──────┘                │    │  │
│  │                                             │                        │    │  │
│  │                                             ▼                        │    │  │
│  │                                       ┌────────────┐                │    │  │
│  │                                       │   Parser   │                │    │  │
│  │                                       │ (HTML/PDF) │                │    │  │
│  │                                       └─────┬──────┘                │    │  │
│  │                                             │                        │    │  │
│  │            ┌────────────────────────────────┼──────────┐            │    │  │
│  │            │                                │          │            │    │  │
│  │            ▼                                ▼          ▼            │    │  │
│  │      ┌──────────┐                    ┌──────────┐ ┌──────────┐     │    │  │
│  │      │   Links  │                    │   Page   │ │ CrawlState│     │    │  │
│  │      │ (queue)  │◀────────────────── │   JSON   │ │  (resume)│     │    │  │
│  │      └────┬─────┘                    └──────────┘ └──────────┘     │    │  │
│  │           │                                                         │    │  │
│  │           └─────────────────loop─────────────────────────────────────┘    │  │
│  │                                                                           │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│         │                                                                       │
│         │  Output: pages/*.json files                                           │
│         │                                                                       │
│         ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 2: INDEX                                                           │  │
│  │  Command: doc-search index https://docs.python.org/3/                     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│         │                                                                       │
│         │  Input: pages/*.json                                                  │
│         │                                                                       │
│         ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                           │  │
│  │   pages/*.json ───────────────────────────────────────────────────┐     │  │
│  │      │                                                             │     │  │
│  │      ▼                                                             │     │  │
│  │   ┌────────────┐    ┌────────────┐    ┌────────────┐              │     │  │
│  │   │  Load JSON │───▶│  Tokenize  │───▶│   Stem     │              │     │  │
│  │   │   (page)   │    │  (words)   │    │  (Porter)  │              │     │  │
│  │   └────────────┘    └────────────┘    └─────┬──────┘              │     │  │
│  │                                             │                      │     │  │
│  │                                             ▼                      │     │  │
│  │                                       ┌────────────┐              │     │  │
│  │                                       │   Weight   │              │     │  │
│  │                                       │ (title 3×) │              │     │  │
│  │                                       └─────┬──────┘              │     │  │
│  │                                             │                      │     │  │
│  │                                             ▼                      │     │  │
│  │                                       ┌────────────┐              │     │  │
│  │   ┌───────────────────────────────────│  BM25Index │              │     │  │
│  │   │                                   │  (update)  │              │     │  │
│  │   │   • inverted index                └────────────┘              │     │  │
│  │   │   • doc frequencies                                           │     │  │
│  │   │   • doc lengths                            │                  │     │  │
│  │   │   • metadata                               │                  │     │  │
│  │   │                                            │                  │     │  │
│  │   └────────────loop────────────────────────────┘                  │     │  │
│  │                                                                    │     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│         │                                                                       │
│         │  Output: index.json.gz                                                │
│         │                                                                       │
│         ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  PHASE 3: SEARCH                                                          │  │
│  │  Command: doc-search search https://docs.python.org/3/ "list methods"     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│         │                                                                       │
│         │  Input: Query string + index.json.gz                                  │
│         │                                                                       │
│         ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                                                                           │  │
│  │   "list methods" ─────────────────────────────────────────────────┐     │  │
│  │      │                                                             │     │  │
│  │      ▼                                                             │     │  │
│  │   ┌────────────┐    ┌────────────┐    ┌────────────┐              │     │  │
│  │   │   Parse    │───▶│  Tokenize  │───▶│  Expand    │              │     │  │
│  │   │  (phrases) │    │   (stem)   │    │ (synonyms) │              │     │  │
│  │   └────────────┘    └────────────┘    └─────┬──────┘              │     │  │
│  │                                             │                      │     │  │
│  │                                             ▼                      │     │  │
│  │   index.json.gz ──────────────────▶ ┌────────────┐              │     │  │
│  │                                       │  BM25      │              │     │  │
│  │                                       │  Scoring   │              │     │  │
│  │                                       └─────┬──────┘              │     │  │
│  │                                             │                      │     │  │
│  │                                             ▼                      │     │  │
│  │                                       ┌────────────┐              │     │  │
│  │                                       │   Filter   │              │     │  │
│  │                                       │ (phrases,  │              │     │  │
│  │                                       │   facets)  │              │     │  │
│  │                                       └─────┬──────┘              │     │  │
│  │                                             │                      │     │  │
│  │                                             ▼                      │     │  │
│  │                                       ┌────────────┐              │     │  │
│  │                                       │   Rank &   │              │     │  │
│  │                                       │  Snippet   │              │     │  │
│  │                                       └─────┬──────┘              │     │  │
│  │                                             │                      │     │  │
│  │                                             ▼                      │     │  │
│  │                                       ┌────────────┐              │     │  │
│  │                                       │  Results   │───▶ CLI/Web │     │  │
│  │                                       │   JSON     │              │     │  │
│  │                                       └────────────┘              │     │  │
│  │                                                                    │     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ═══════════════════════════════════════════════════════════════════════════   │
│                                                                                 │
│  DATA TRANSFORMATION SUMMARY:                                                   │
│                                                                                 │
│  URL ─────────▶ HTML ─────────▶ Text+Metadata ─────────▶ page.json             │
│                 fetch           parse                    store                  │
│                                                                                 │
│  pages/*.json ─▶ Tokens ─────▶ Term Frequencies ───────▶ index.json.gz         │
│                  tokenize       aggregate                 serialize             │
│                                                                                 │
│  Query ───────▶ Tokens ─────▶ BM25 Scores ─────────────▶ Ranked Results        │
│                  tokenize      score & rank               format                │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Module Interaction Summary

The following table summarizes which modules are involved at each pipeline stage:

| Stage | Primary Module | Supporting Modules |
|-------|---------------|-------------------|
| **URL Normalization** | `core/text.py` / `core/urls.py` | - |
| **Robots Check** | `crawl/robots.py` | `core/text.py` / `core/urls.py` |
| **Rate Limiting** | `crawl/rate_limiter.py` | - |
| **HTTP Fetch** | `crawl/crawler.py` | `core/text.py` / `core/urls.py` |
| **HTML Parse** | `extract/html.py` | - |
| **PDF Extract** | `extract/pdf.py` | - |
| **State Management** | `crawl/state.py` | - |
| **Tokenization** | `core/text.py` / `core/urls.py` | `core/stemmer.py` |
| **Index Build** | `index/store.py` | `core/text.py` / `core/urls.py`, `core/stemmer.py` |
| **Query Parse** | `search/engine.py` | `core/text.py` / `core/urls.py` |
| **BM25 Search** | `index/store.py` | - |
| **Spellcheck** | `search/features/spellcheck.py` | - |
| **Autocomplete** | `search/features/suggester.py` | - |
| **Synonyms** | `search/features/synonyms.py` | - |
| **Facets** | `search/features/facets.py` | - |
| **Snippets** | `search/snippets.py` | - |
| **CLI Interface** | `app/cli/` | All above |
| **Web Interface** | `app/server.py` | `search/engine.py` |

## Extending doc-search

### Adding a New Command
1. Add command function in `cli/commands.py`
2. Add argument parser in `cli/parsers.py`
3. Register in `cli/__init__.py`

### Adding a New Search Feature
1. Add a module under `doc_search/search/features/`.
2. Register it from `EnhancedSearchEngine` in `search/engine.py` (or a
   feature list passed into the engine). Do **not** import it from `app`.
3. Never import `app` or `crawl` from a feature module.

### Custom Tokenization
Edit `doc_search/core/text.py`:
- Modify `STOP_WORDS` for different languages
- Adjust regex in `tokenize()` for different word patterns
