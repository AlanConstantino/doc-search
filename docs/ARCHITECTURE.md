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

```
doc_search/
├── __init__.py           # Package info, version
├── __main__.py           # Entry point (python -m doc_search)
│
├── cli/                  # Command-line interface
│   ├── __init__.py       # CLI entry point (main function)
│   ├── commands.py       # Command implementations
│   └── parsers.py        # Argument parsing
│
├── crawler.py            # Web crawler engine
├── crawl_state.py        # Crawl state persistence
├── rate_limiter.py       # Request rate limiting
├── robots.py             # robots.txt parsing
├── parser.py             # HTML text extraction
├── pdf_extractor.py      # PDF text extraction
│
├── indexer.py            # BM25 index builder
├── stemmer.py            # Porter stemmer
│
├── searcher.py           # Search engine
├── searcher_utils.py     # Result formatting/highlighting
├── spellcheck.py         # "Did you mean..." suggestions
├── autocomplete.py       # Type-ahead suggestions
├── facets.py             # Category filtering
├── synonyms.py           # Query expansion
│
├── server.py             # Web UI server
├── utils.py              # Shared utilities
└── constants.py          # Configuration values
```

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
- **Crawler** (`crawler.py`): Orchestrates the crawl, manages URL queue
- **CrawlState** (`crawl_state.py`): Tracks visited URLs, enables resume
- **RateLimiter** (`rate_limiter.py`): Enforces delays between requests
- **RobotsChecker** (`robots.py`): Respects robots.txt rules
- **HTMLTextExtractor** (`parser.py`): Extracts text from HTML
- **PDFExtractor** (`pdf_extractor.py`): Extracts text from PDFs

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
- **BM25Index** (`indexer.py`): Builds inverted index with BM25 statistics
- **tokenize()** (`utils.py`): Splits text into searchable tokens
- **stem()** (`stemmer.py`): Reduces words to root forms

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
- **SearchEngine** (`searcher.py`): Query processing and result ranking
- **SpellChecker** (`spellcheck.py`): "Did you mean..." suggestions
- **Autocomplete** (`autocomplete.py`): Type-ahead completions
- **Facets** (`facets.py`): URL path categorization
- **Synonyms** (`synonyms.py`): Query expansion
- **searcher_utils** (`searcher_utils.py`): Result formatting

## Module Dependencies

```
                           ┌─────────────────┐
                           │    constants    │
                           └────────┬────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
       ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
       │    utils    │       │   stemmer   │       │  spellcheck │
       └──────┬──────┘       └──────┬──────┘       └─────────────┘
              │                     │
    ┌─────────┼─────────┬───────────┼───────────┐
    │         │         │           │           │
    ▼         ▼         ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│ parser │ │ robots │ │indexer │ │searcher│ │ server │
└────────┘ └────────┘ └───┬────┘ └───┬────┘ └───┬────┘
    │                     │          │          │
    └─────────┬───────────┘          │          │
              ▼                      │          │
         ┌─────────┐                 │          │
         │ crawler │                 │          │
         └────┬────┘                 │          │
              │                      │          │
              └──────────────────────┴──────────┘
                                     │
                                     ▼
                              ┌─────────────┐
                              │    cli/     │
                              │  commands   │
                              │  parsers    │
                              └─────────────┘
```

## Storage Layout

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
| `DEFAULT_BM25_K1` | 1.5 | Term frequency saturation |
| `DEFAULT_BM25_B` | 0.75 | Length normalization |
| `DEFAULT_CRAWL_DELAY` | 1.0s | Delay between requests |
| `CHECKPOINT_INTERVAL` | 100 | Pages between state saves |
| `STEM_CACHE_SIZE` | 10,000 | Stemmer LRU cache size |

## Extending doc-search

### Adding a New Command
1. Add command function in `cli/commands.py`
2. Add argument parser in `cli/parsers.py`
3. Register in `cli/__init__.py`

### Adding a New Search Feature
1. Create module in `doc_search/`
2. Import in `searcher.py`
3. Integrate with search pipeline

### Custom Tokenization
Edit `utils.py`:
- Modify `STOP_WORDS` for different languages
- Adjust regex in `tokenize()` for different word patterns
