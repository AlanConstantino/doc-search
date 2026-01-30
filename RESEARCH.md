# Research: Large-Scale Documentation Search

## Overview
Building a search tool for 5,000-15,000 page technical documentation sites requires careful consideration of crawling efficiency, storage, indexing, and search quality.

---

## 1. Crawling Strategies

### 1.1 Breadth-First vs Depth-First
- **Breadth-First Search (BFS)**: Better for documentation sites - captures all top-level pages first, then dives deeper. More predictable memory usage.
- **Depth-First Search (DFS)**: Can get stuck in deep hierarchies. Not recommended for large sites.
- **Recommendation**: BFS with URL priority queue based on path depth.

### 1.2 Politeness & Rate Limiting
- **Crawl-Delay**: Respect robots.txt `Crawl-delay` directive (typically 1-10 seconds)
- **Default Delay**: 1-2 seconds between requests is industry standard
- **Adaptive Throttling**: Slow down on 429/503 responses, back off exponentially
- **Concurrent Connections**: Single connection for politeness, or 2-3 max with longer delays

### 1.3 robots.txt Compliance
- Parse `User-agent`, `Disallow`, `Allow`, `Crawl-delay`
- Cache robots.txt (refresh every 24 hours for long crawls)
- Standard library `urllib.robotparser` handles this

### 1.4 Resumable Crawls
- **Frontier Persistence**: Save URL queue and visited set to disk
- **Checkpoint Strategy**: Save state every N pages (e.g., every 100)
- **Format**: JSON or pickle for quick serialization
- **State to Track**: 
  - Visited URLs (set)
  - Pending URLs (deque)
  - Failed URLs (for retry)
  - Crawl metadata (start time, pages crawled)

### 1.5 URL Normalization
Essential to avoid duplicate crawls:
- Lowercase scheme and host
- Remove default ports (80, 443)
- Remove fragments (#anchor)
- Sort query parameters
- Handle trailing slashes consistently

---

## 2. HTML Text Extraction

### 2.1 Approaches
1. **Regex-based**: Fast but fragile, struggles with nested tags
2. **html.parser (stdlib)**: Good balance of speed and accuracy
3. **Custom parser**: More control, handle documentation-specific patterns

### 2.2 Content Extraction Strategy
- Remove `<script>`, `<style>`, `<nav>`, `<header>`, `<footer>` tags
- Extract from `<main>`, `<article>`, or `<div class="content">` when present
- Preserve structure: headers become weighted terms
- Handle code blocks specially (may want to index or exclude)

### 2.3 Metadata Extraction
- Title from `<title>` or `<h1>`
- Description from `<meta name="description">`
- Last modified from `<meta>` or HTTP headers

---

## 3. Search Algorithms

### 3.1 TF-IDF (Term Frequency-Inverse Document Frequency)
**Formula:**
- TF(t,d) = count of term t in document d / total terms in d
- IDF(t) = log(N / df(t)) where N = total docs, df(t) = docs containing t
- Score = TF × IDF

**Pros:**
- Simple to implement
- Fast to compute
- Works well for keyword matching

**Cons:**
- No term saturation (more = always better)
- Document length bias

### 3.2 BM25 (Best Match 25)
**Formula:**
```
score(D,Q) = Σ IDF(qi) × (f(qi,D) × (k1 + 1)) / (f(qi,D) + k1 × (1 - b + b × |D|/avgdl))
```

**Parameters:**
- k1 (1.2-2.0): Term frequency saturation. Higher = more weight to frequency
- b (0.75): Length normalization. 0 = no normalization, 1 = full normalization

**Pros:**
- Handles term saturation (diminishing returns for repeated terms)
- Length normalization built-in
- Industry standard (Elasticsearch, Lucene default)

**Cons:**
- More complex implementation
- Parameter tuning may be needed

### 3.3 Recommendation: BM25
BM25 is the clear winner for documentation search:
- Better handling of varying document lengths (API docs vs tutorials)
- Proven performance across information retrieval benchmarks
- Standard parameters (k1=1.5, b=0.75) work well out of box

---

## 4. Indexing Methods

### 4.1 Inverted Index
Core data structure for text search:
```
{
  "term1": [(doc_id, frequency, [positions]), ...],
  "term2": [(doc_id, frequency, [positions]), ...],
}
```

### 4.2 Storage Considerations for 15K Pages
Estimates for technical documentation:
- Average page: 5KB text → 500-1000 unique terms
- Total unique terms: ~50,000-100,000
- Index size: ~50-100MB (uncompressed JSON)
- Memory usage: Feasible to keep in RAM

### 4.3 Optimization Techniques
- **Stemming**: Reduce words to roots (optional, adds complexity)
- **Stop words**: Remove common words (the, a, is) - significant space savings
- **Term frequency threshold**: Skip terms appearing in >50% of docs
- **Compression**: gzip index files for storage

### 4.4 Persistence Format
- **JSON**: Human-readable, stdlib support, moderate size
- **Pickle**: Faster load/save, but version-sensitive
- **Recommendation**: JSON with optional gzip compression

---

## 5. Implementation Architecture

### 5.1 Module Structure
```
doc_search/
├── __init__.py
├── __main__.py          # CLI entry point
├── crawler.py           # Web crawler with resumable state
├── parser.py            # HTML text extraction
├── indexer.py           # BM25 index building
├── searcher.py          # Query processing and ranking
├── robots.py            # robots.txt handling
└── utils.py             # URL normalization, helpers
```

### 5.2 Data Files
```
~/.doc_search/
├── sites/
│   └── {site_hash}/
│       ├── crawl_state.json   # Resumable crawl state
│       ├── pages/             # Cached page content
│       ├── index.json         # Search index
│       └── metadata.json      # Site info, crawl stats
```

### 5.3 Memory Management
For 15K pages:
- Don't load all pages into memory simultaneously
- Stream processing during index building
- Keep index in memory (50-100MB is acceptable)
- Use generators where possible

---

## 6. HTTP Basic Auth Implementation

### 6.1 Standard Library Approach
```python
import base64
import urllib.request

credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
headers = {"Authorization": f"Basic {credentials}"}
request = urllib.request.Request(url, headers=headers)
```

### 6.2 Security Considerations
- Never store credentials in plain text
- Use environment variables or prompt for credentials
- HTTPS only for auth'd requests

---

## 7. Error Handling & Resilience

### 7.1 Network Errors
- Timeout: 30 seconds default, retry with backoff
- Connection errors: Retry 3 times, then skip
- HTTP 429 (rate limit): Exponential backoff, respect Retry-After header
- HTTP 5xx: Retry with backoff
- HTTP 4xx: Log and skip (except 429)

### 7.2 Content Errors
- Invalid HTML: Best-effort parsing
- Empty pages: Skip indexing
- Binary content: Detect via Content-Type, skip

---

## 8. Conclusions

### Recommended Approach
1. **Crawler**: BFS with single-threaded requests, 1-2s delay, robots.txt compliance
2. **Parser**: stdlib html.parser with nav/script/style removal
3. **Index**: Inverted index with BM25 scoring
4. **Storage**: JSON files with gzip compression option
5. **Resume**: Checkpoint every 100 pages, save frontier state

### Expected Performance
- Crawl rate: ~30-60 pages/minute (with 1s delay)
- 15K pages: 4-8 hours crawl time
- Index build: ~5-10 minutes
- Search latency: <100ms for typical queries
- Storage: ~100-200MB total (pages + index)

### Trade-offs Made
- Single-threaded for simplicity and politeness
- JSON over binary for debuggability
- No stemming (complexity vs benefit for technical docs)
- In-memory index (acceptable for target scale)
