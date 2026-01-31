# doc-search: Bugs & Improvement Suggestions

**Date:** 2026-01-30  
**Tested Version:** 1.7.0  
**Test Status:** All 145 unit tests pass ✓

---

## 📦 v1.7.0 Changes Summary

This release focuses on making doc-search work seamlessly with any documentation site:

### Domain-Agnostic Facets
- Facet extraction now uses URL path structure directly instead of hardcoded patterns
- Works with Python docs, Docusaurus, ReadTheDocs, corporate docs, and more
- Categories extracted from first path segment, subcategories from second
- Skips generic parts (`docs`, `en`, version numbers) automatically

### Opt-in Synonyms
- Synonym expansion is now **disabled by default** (was enabled)
- Prevents unwanted query expansion that could reduce precision
- Enable with `--synonyms` flag for built-in programming terms
- Use `--synonyms-file FILE` for custom synonym groups (JSON format)

### Pagination
- Web UI now paginates results (10 per page, configurable)
- Supports up to 100 results total
- Pure HTML navigation (Previous/Next, page numbers)
- No JavaScript required

---

## 🐛 Bugs Found

### 1. URL Path Normalization Doesn't Resolve `..` or `.`

**Severity:** Medium  
**Location:** `utils.py` → `normalize_url()`

**Problem:** The URL normalizer doesn't canonicalize paths with `..` or `.`, which can cause:
- Duplicate crawls of the same page via different paths
- Inconsistent URL matching

**Reproduction:**
```python
from doc_search.utils import normalize_url
normalize_url("http://example.com/a/../b")  # Returns: http://example.com/a/../b
# Expected: http://example.com/b
```

**Fix:** Use `posixpath.normpath()` or `urllib.parse.urljoin` with an empty base to resolve path:
```python
from urllib.parse import urlparse, urlunparse
import posixpath

def normalize_url(url):
    parsed = urlparse(url)
    normalized_path = posixpath.normpath(parsed.path) or '/'
    # ... rest of normalization
```

---

### 2. Unquoted `href` Attributes Not Extracted

**Severity:** Low  
**Location:** `parser.py` → `extract_links()`

**Problem:** The regex only matches quoted hrefs, missing valid HTML like:
```html
<a href=page.html>Link</a>
```

**Current Regex:** `r'<a[^>]+href=["\']([^"\']+)["\']'`

**Fix:** Update regex to also match unquoted values:
```python
href_pattern = re.compile(
    r'<a[^>]+href=(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))',
    re.IGNORECASE
)
```

---

### 3. Hyphenated Words Create Phrase Match False Positives

**Severity:** Low (arguably a feature)  
**Location:** `searcher.py` → `check_phrase_match()`

**Problem:** Searching for `"quick brown"` matches `quick-brown` because tokenization removes the hyphen:
```python
tokenize("quick-brown")  # Returns: ['quick', 'brown']
check_phrase_match("quick-brown", ["quick", "brown"])  # Returns: True
```

**This could be intentional** (treating hyphens as word separators), but may cause unexpected matches.

**Fix Options:**
1. Document this behavior (if intentional)
2. Track token positions in original text and verify adjacency in source

---

## ⚠️ Potential Issues (Not Bugs)

### 1. SSL Verification Disabled

**Location:** `crawler.py`  
**Current:** `ssl.CERT_NONE`

This is documented and intentional (for self-signed certs in internal docs), but worth noting:
- Could be a security concern when crawling untrusted sites
- Consider making it opt-in via CLI flag

### 2. CrawlState Memory Usage

**Location:** `crawler.py` → `CrawlState`

The `visited` set grows unbounded and stays in memory. For very large sites (100K+ pages), this could be an issue.

**Future Option:** Use a Bloom filter for visited URLs (probabilistic but memory-efficient).

### 3. Single-Letter Terms Silently Filtered

**Location:** `utils.py` → `tokenize()`

Words with `len <= 1` are filtered out, which could surprise users:
```python
tokenize("a b c d")  # Returns: []
```

This is intentional (noise reduction) but undocumented.

---

## 🚀 Improvement Suggestions

### High Priority

#### 1. Add `--verify-ssl` Flag
Allow users to opt-in to SSL verification for security-conscious crawls:
```bash
python -m doc_search crawl https://docs.example.com --verify-ssl
```

#### 2. Progress Bar for Long Operations
Add optional progress bars using `\r` carriage returns (stdlib compatible):
```
Crawling: [████████░░░░░░░░░░░░] 42% (2100/5000 pages)
```

#### 3. Export to JSON/CSV
Add export command for search results:
```bash
python -m doc_search export https://docs.example.com --format json > results.json
```

#### 4. Configurable Stop Words
Allow users to customize stop words via file:
```bash
python -m doc_search index site --stopwords custom_stopwords.txt
```

### Medium Priority

#### 5. Incremental Index Updates
Currently, re-indexing requires rebuilding from scratch. Support incremental updates:
```bash
python -m doc_search index site --update  # Only index new/changed pages
```

#### 6. Search Result Caching
Cache recent search results to speed up repeated queries (especially useful for web UI).

#### 7. Custom Crawl Rules
Support user-defined URL include/exclude patterns:
```bash
python -m doc_search crawl https://docs.example.com \
  --include "/api/*" --exclude "/archive/*"
```

#### 8. Health Check Endpoint for Web Server
Add `/health` endpoint for monitoring:
```
GET /health → {"status": "ok", "docs": 5000, "uptime": 3600}
```

### Low Priority (Nice to Have)

#### 9. Multiple Index Support
Allow searching across multiple sites simultaneously:
```bash
python -m doc_search search --sites "python,django" "async views"
```

#### 10. Search Analytics
Track popular queries and zero-result queries for debugging:
```bash
python -m doc_search analytics site
```

#### 11. Sitemap.xml Support
Use sitemap.xml for more efficient crawling when available:
```bash
python -m doc_search crawl https://docs.example.com --use-sitemap
```

#### 12. Rate Limit Auto-Detection
Automatically adjust crawl delay based on response times and 429s.

---

## 📝 Documentation Improvements

1. **Add CHANGELOG.md** - Track version changes systematically
2. **Document tokenization behavior** - Explain what gets filtered (stopwords, short words)
3. **Add architecture diagram** - Visual overview of module relationships
4. **Troubleshooting guide** - Common issues and solutions
5. **Performance tuning guide** - BM25 parameter tuning, optimal crawl settings

---

## 🧪 Test Coverage Gaps

While the existing tests are comprehensive, consider adding:

1. **End-to-end CLI tests** - Test actual command execution
2. **Web server integration tests** - Test HTTP responses
3. **Concurrent crawl tests** - Stress test parallel workers
4. **Large dataset benchmarks** - Performance regression tests
5. **Malformed HTML corpus** - Test against real-world messy HTML

---

## Summary

| Category | Count |
|----------|-------|
| **Bugs** | 3 |
| **Potential Issues** | 3 |
| **High Priority Improvements** | 4 |
| **Medium Priority Improvements** | 4 |
| **Low Priority Improvements** | 4 |

**Overall Assessment:** The codebase is solid with good test coverage. The bugs found are minor edge cases. The architecture is clean and well-documented. Most improvements are feature enhancements rather than fixes.
