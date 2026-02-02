# doc-search Refactor Plan v2.0

**Created:** 2025-01-20  
**Version Analyzed:** v1.9.0 (post major refactor)  
**Total Issues Found:** 42  
**Codebase Size:** 6,530 lines across 22 Python files  
**Test Coverage:** 459 tests passing (100%)

---

## Executive Summary

The v1.9.0 release addressed 30 issues from the original refactor plan. The codebase is now in solid shape with:
- ✅ Constants extracted to central module
- ✅ BM25 parameter validation
- ✅ LRU cache on stemmer
- ✅ Server health endpoint
- ✅ Comprehensive test coverage for core modules
- ✅ Thread-safe crawl state

**Remaining opportunities for improvement:**
1. **Test Coverage Gaps** - CLI module has 0 tests (788 lines)
2. **Large File Decomposition** - `crawler.py` (833 lines), `server.py` (782 lines)
3. **API Inconsistency** - Mixed return types between `SearchEngine` and `EnhancedSearchEngine`
4. **Documentation Gaps** - Some modules lack comprehensive docstrings
5. **Error Handling** - Inconsistent patterns across modules

---

## Issues by Category

### Category 1: Test Coverage Gaps (HIGH PRIORITY)

---

### 1.1: CLI Commands Module Has No Tests
**File:** `doc_search/cli/commands.py`  
**Lines:** 579 lines, 0% test coverage  
**Severity:** High  
**Effort:** Large

**Description:**
The entire CLI commands module (`cmd_crawl`, `cmd_index`, `cmd_search`, `cmd_serve`, etc.) has no test coverage. This is the highest-risk area of the codebase.

**Why It's a Problem:**
- CLI is the primary user interface - bugs here directly impact users
- 579 lines of untested code handling file I/O, network operations, user input
- Refactoring CLI is risky without tests as a safety net
- Can't verify behavior changes or catch regressions

**Recommended Fix:**
1. Create `tests/test_cli.py`
2. Add unit tests for each command function using temporary directories
3. Mock external dependencies (crawler, indexer, server)
4. Test argument parsing edge cases
5. Test error handling paths

**Test Cases Needed:**
- `cmd_crawl`: Valid URL, invalid URL, authentication options
- `cmd_index`: Existing pages, empty pages dir, BM25 params
- `cmd_search`: Basic search, JSON output, facet filters
- `cmd_serve`: Server startup/shutdown, port binding
- `cmd_stats`: With/without metadata, with/without errors

---

### 1.2: CLI Parsers Module Has No Tests
**File:** `doc_search/cli/parsers.py`  
**Lines:** 209 lines, 0% test coverage  
**Severity:** Medium  
**Effort:** Medium

**Description:**
Argument parsers define the entire CLI interface but have no tests verifying argument parsing.

**Why It's a Problem:**
- Argument parsing bugs cause poor UX (confusing error messages)
- No verification that help text is accurate
- Can't catch missing required arguments or wrong types

**Recommended Fix:**
1. Add tests for each subparser
2. Test argument combinations and defaults
3. Test invalid argument handling

---

### 1.3: Integration Tests Between Modules Missing
**File:** N/A (cross-module)  
**Severity:** Medium  
**Effort:** Large

**Description:**
No end-to-end tests verify the full workflow: crawl → index → search.

**Why It's a Problem:**
- Individual module tests pass but integration could fail
- Version compatibility issues between index format and loader
- Can't verify the "happy path" user experience

**Recommended Fix:**
1. Create `tests/test_integration.py`
2. Test full crawl → index → search cycle with mock HTTP
3. Test index save/load round-trip with search verification

---

### Category 2: Large/Complex Files

---

### 2.1: Crawler Module Too Large
**File:** `doc_search/crawler.py`  
**Lines:** 833 lines  
**Severity:** Medium  
**Effort:** Large

**Description:**
The crawler module contains multiple responsibilities:
- HTTP fetching with retry logic
- URL filtering and validation
- Page processing and link extraction
- Parallel execution management
- Document (PDF) extraction coordination

**Why It's a Problem:**
- Hard to understand the full flow
- Changes to one feature risk breaking others
- Testing requires mocking many things
- Single 833-line file is intimidating for contributors

**Recommended Fix:**
Extract into focused modules:
```
doc_search/
├── crawler/
│   ├── __init__.py      # Exports Crawler class
│   ├── fetcher.py       # HTTP fetching, retry, rate limiting
│   ├── url_filter.py    # URL validation, extension checks
│   ├── processor.py     # Page processing, link extraction
│   └── parallel.py      # ThreadPoolExecutor management
```

**Incremental Approach:**
1. Extract `_fetch()` method to `fetcher.py` (standalone, no Crawler dependency)
2. Extract URL filtering predicates to `url_filter.py`
3. Keep `Crawler` as orchestrator that composes these modules

---

### 2.2: Server Module Too Large
**File:** `doc_search/server.py`  
**Lines:** 782 lines  
**Severity:** Medium  
**Effort:** Medium

**Description:**
The server module mixes:
- CSS styles (250+ lines as string constant)
- HTML template rendering logic
- HTTP request handling
- Response formatting

**Why It's a Problem:**
- CSS as a Python string is hard to maintain
- No syntax highlighting or CSS tooling
- Template logic mixed with HTTP handling
- Can't easily change styling without touching Python

**Recommended Fix:**
1. Extract CSS to a separate file (or keep inline for zero-dependency goal)
2. Extract template functions to `templates.py`
3. Keep `server.py` focused on HTTP handling only

**Alternative (Simpler):**
Move CSS constant to top of file with clear section header.
This maintains the zero-dependency philosophy while improving organization.

---

### Category 3: API Inconsistency

---

### 3.1: SearchEngine vs EnhancedSearchEngine Return Types
**File:** `doc_search/searcher.py`  
**Lines:** Various  
**Severity:** Medium  
**Effort:** Medium

**Description:**
`SearchEngine.search()` returns `List[Dict]`  
`EnhancedSearchEngine.search()` returns `Dict[str, Any]` with nested `results`

**Why It's a Problem:**
- Breaks Liskov Substitution Principle (subclass can't substitute parent)
- Code using `SearchEngine` can't easily switch to `EnhancedSearchEngine`
- `search_simple()` exists as a workaround, adding API surface

**Current Code:**
```python
# SearchEngine
def search(self, query, ...) -> List[Dict[str, Any]]:
    ...

# EnhancedSearchEngine  
def search(self, query, ...) -> Dict[str, Any]:  # Different return type!
    return {'results': [...], 'suggestion': ..., 'facets': ...}

def search_simple(self, query, ...) -> List[Dict[str, Any]]:  # Workaround
    response = self.search(query, ...)
    return response['results']
```

**Recommended Fix:**
Option A (Breaking change): Make both return `Dict[str, Any]`
Option B (Non-breaking): Deprecate `search_simple`, document return type difference
Option C (Composition): `EnhancedSearchEngine` wraps `SearchEngine` instead of inheriting

---

### 3.2: Inconsistent Error Handling Return Patterns
**File:** Multiple  
**Severity:** Low  
**Effort:** Medium

**Description:**
Different modules return errors differently:
- `PDFExtractor`: Returns `{'error': 'message', 'text': ''}` 
- `Crawler._fetch()`: Returns `(None, None, {'error_type': ..., 'error_message': ...})`
- `CrawlState.load()`: Returns `False` on error

**Why It's a Problem:**
- Inconsistent patterns make code harder to learn
- Easy to forget to check for errors
- No unified error type

**Recommended Fix:**
Standardize on one pattern:
1. Return dataclass with optional error field (preferred)
2. Document error handling pattern in CONTRIBUTING.md

---

### Category 4: Documentation Gaps

---

### 4.1: Missing Module-Level Docstrings
**Files:** `doc_search/cli/__init__.py`, `doc_search/crawl_state.py`  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
Some modules lack module-level docstrings explaining their purpose.

**Recommended Fix:**
Add docstrings to:
- `crawl_state.py` (has good inline docs but no module docstring)
- `rate_limiter.py` (minimal docs)

---

### 4.2: Missing API Documentation
**File:** `docs/`  
**Severity:** Medium  
**Effort:** Medium

**Description:**
No API documentation exists for programmatic usage of doc-search as a library.

**Why It's a Problem:**
- Users who want to embed doc-search in their app have no guidance
- Class/method relationships unclear without reading code
- No examples of library usage (vs CLI usage)

**Recommended Fix:**
1. Create `docs/API.md` with:
   - Core classes: `BM25Index`, `SearchEngine`, `Crawler`
   - Common patterns and examples
   - Index format specification

---

### 4.3: docs/ARCHITECTURE.md Could Be Expanded
**File:** `docs/ARCHITECTURE.md`  
**Lines:** 16,883 characters  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
Architecture doc exists but doesn't cover:
- Data flow diagrams
- Thread safety model
- Extension points

**Recommended Fix:**
Add sections on:
- How crawler state persistence works
- Thread safety guarantees
- How to add new search features

---

### Category 5: Code Duplication

---

### 5.1: Auth Header Generation Duplicated
**Files:** `crawler.py`, `pdf_extractor.py`  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
Both `Crawler._get_auth_header()` and `PDFExtractor._get_auth_header()` implement identical Basic Auth header generation.

**Current Code (duplicated):**
```python
def _get_auth_header(self) -> Optional[str]:
    if self.auth_token:
        token = self.auth_token
        if token.lower().startswith('basic '):
            token = token[6:]
        return f"Basic {token}"
    if self.auth:
        username, password = self.auth
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    return None
```

**Recommended Fix:**
Extract to `utils.py`:
```python
def make_basic_auth_header(
    auth: Optional[Tuple[str, str]] = None,
    auth_token: Optional[str] = None
) -> Optional[str]:
    ...
```

---

### 5.2: SSL Context Creation Duplicated
**Files:** `crawler.py`, `pdf_extractor.py`  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
Both modules create identical SSL contexts that skip verification:
```python
self.ssl_context = ssl.create_default_context()
self.ssl_context.check_hostname = False
self.ssl_context.verify_mode = ssl.CERT_NONE
```

**Recommended Fix:**
Extract to `utils.py`:
```python
def create_permissive_ssl_context() -> ssl.SSLContext:
    """Create SSL context that skips certificate verification."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
```

---

### Category 6: Performance Opportunities

---

### 6.1: Inefficient Pending URL Deduplication
**File:** `doc_search/crawl_state.py`  
**Lines:** 74-81  
**Severity:** Medium  
**Effort:** Medium

**Description:**
`add_urls()` builds a set from the deque on every call for deduplication:
```python
def add_urls(self, urls: List[Tuple[str, int]]):
    with self._lock:
        # O(n) set construction on every call
        pending_urls = {url for url, _ in self.pending}
        for url, depth in urls:
            if url not in self.visited and url not in pending_urls:
                self.pending.append((url, depth))
                pending_urls.add(url)
```

**Why It's a Problem:**
- O(n) operation on every `add_urls()` call
- With 10,000+ URLs in queue, this becomes slow
- Called frequently during crawling

**Recommended Fix:**
Maintain a persistent `pending_urls` set alongside the deque:
```python
def __init__(self):
    self.pending: deque = deque()
    self._pending_set: Set[str] = set()  # For O(1) lookup

def add_urls(self, urls: List[Tuple[str, int]]):
    with self._lock:
        for url, depth in urls:
            if url not in self.visited and url not in self._pending_set:
                self.pending.append((url, depth))
                self._pending_set.add(url)

def pop_url(self) -> Optional[Tuple[str, int]]:
    with self._lock:
        if self.pending:
            item = self.pending.popleft()
            self._pending_set.discard(item[0])
            return item
        return None
```

---

### 6.2: Snippet Finding Tokenizes Entire Document
**File:** `doc_search/searcher_utils.py`  
**Lines:** 77-139  
**Severity:** Low  
**Effort:** Medium

**Description:**
`find_best_snippet()` tokenizes the entire document to find the best window:
```python
word_pattern = re.compile(r'\b[a-zA-Z][a-zA-Z0-9_]*\b')
matches = list(word_pattern.finditer(text))  # Finds ALL words
```

**Why It's a Problem:**
- For large documents (50KB+), this creates thousands of match objects
- Most of these are never used (we only need ~20 words around matches)
- Memory allocation for large lists

**Recommended Fix:**
1. First find query term positions
2. Only tokenize windows around those positions
3. Or: Accept current behavior as "good enough" (simple, correct, not hot path)

---

### 6.3: Index Loading Deserializes All Documents
**File:** `doc_search/indexer.py`  
**Lines:** 209-225  
**Severity:** Low  
**Effort:** Large

**Description:**
`BM25Index.load()` deserializes the entire index into memory, including all document metadata.

**Why It's a Problem:**
- For very large indexes (100K+ docs), memory usage grows linearly
- Documents dict stores URL, title, description for every page
- Most searches only return top 10-100 results

**Recommended Fix (if needed):**
Lazy loading / memory-mapped index. However, this is likely over-engineering for the target use case (5K-15K pages).

**Recommendation:** Document expected memory usage, don't change unless proven necessary.

---

### Category 7: Tight Coupling

---

### 7.1: Circular Import Potential in Utils
**File:** `doc_search/utils.py`  
**Lines:** 256-257  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
`tokenize()` has a conditional import inside the function:
```python
if stem:
    from .stemmer import stem as stem_word
    tokens = [stem_word(t) for t in tokens]
```

**Why It's a Problem:**
- Import inside function is a code smell
- Indicates potential circular dependency
- Slightly slower (import on each call, though cached)

**Recommended Fix:**
Move import to top of file. The current pattern exists to avoid circular imports, but with proper module organization this shouldn't be needed.

---

### 7.2: Searcher Directly Accesses Index Internals
**File:** `doc_search/searcher.py`  
**Lines:** 171-172, 273-274  
**Severity:** Low  
**Effort:** Medium

**Description:**
`EnhancedSearchEngine` directly accesses `index.doc_freqs` and `index.documents`:
```python
self._autocomplete.build_from_index(dict(self.index.doc_freqs))
for doc_id, doc in self.index.documents.items():
```

**Why It's a Problem:**
- Tight coupling to internal data structures
- Index implementation changes break searcher
- No abstraction boundary

**Recommended Fix:**
Add accessor methods to `BM25Index`:
```python
def get_term_frequencies(self) -> Dict[str, int]:
    return dict(self.doc_freqs)

def iter_documents(self) -> Iterator[Tuple[int, Dict[str, Any]]]:
    return self.documents.items()
```

---

### Category 8: Naming Inconsistencies

---

### 8.1: Mixed Naming Conventions for Private Methods
**Files:** Multiple  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
Some private methods use single underscore, others don't:
- `Crawler._fetch()` ✓
- `Crawler._should_crawl()` ✓
- `CrawlState.pop_url()` (no underscore, but internal-ish)
- `RateLimiter.wait_for_domain()` (public API, correct)

**Why It's a Problem:**
- Inconsistent signals about public vs private API
- Documentation needs to clarify what's stable

**Recommended Fix:**
1. Audit all methods
2. Mark truly private methods with `_` prefix
3. Document public API in docstrings

---

### 8.2: `stem` Variable Name Shadows Module
**File:** `doc_search/utils.py`  
**Lines:** 244-256  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
The `tokenize()` function has a parameter `stem: bool` which shadows the import:
```python
def tokenize(text: str, stem: bool = False) -> list:
    if stem:
        from .stemmer import stem as stem_word  # Renamed to avoid shadow
```

**Why It's a Problem:**
- Confusing naming (had to rename import)
- Easy to accidentally use wrong `stem`

**Recommended Fix:**
Rename parameter to `apply_stemming` or `use_stemmer`:
```python
def tokenize(text: str, apply_stemming: bool = False) -> list:
```

---

### Category 9: Error Handling Improvements

---

### 9.1: Silent Failures in Page Iteration
**File:** `doc_search/crawler.py`  
**Lines:** 690-695  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
`get_crawled_pages()` silently skips corrupted JSON files:
```python
def get_crawled_pages(self):
    for page_file in self.pages_dir.glob('*.json'):
        try:
            with open(page_file, 'r') as f:
                yield json.load(f)
        except (json.JSONDecodeError, IOError):
            continue  # Silent failure
```

**Why It's a Problem:**
- No way to know if pages were skipped
- Debugging corrupted files is hard
- Index might be incomplete without warning

**Recommended Fix:**
Add optional verbose/logging parameter:
```python
def get_crawled_pages(self, warn_on_error: bool = True):
    for page_file in self.pages_dir.glob('*.json'):
        try:
            with open(page_file, 'r') as f:
                yield json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            if warn_on_error:
                print(f"Warning: Skipping corrupted file {page_file}: {e}")
            continue
```

---

### 9.2: Generic Exception Handling in Parser
**File:** `doc_search/parser.py`  
**Lines:** 166-168  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
`extract_text()` catches all exceptions:
```python
try:
    extractor.feed(html)
except Exception:
    pass  # Handle malformed HTML gracefully
```

**Why It's a Problem:**
- Catches programming errors (typos, None, etc.)
- No logging or visibility into failures
- Could mask real bugs

**Recommended Fix:**
Catch specific exceptions:
```python
try:
    extractor.feed(html)
except (HTMLParseError, ValueError, TypeError) as e:
    # Log or track parsing failures
    pass
```

---

### Category 10: Security/Reliability

---

### 10.1: SSL Certificate Verification Disabled
**Files:** `crawler.py`, `pdf_extractor.py`  
**Severity:** Medium (intentional, but should document)  
**Effort:** Quick Win

**Description:**
Both modules disable SSL certificate verification:
```python
self.ssl_context.check_hostname = False
self.ssl_context.verify_mode = ssl.CERT_NONE
```

**Why It Exists:**
Documentation sites often have self-signed or expired certificates, and users want to crawl them anyway.

**Why It's a Concern:**
- Man-in-the-middle attacks possible
- Could crawl malicious content
- Credentials sent to wrong server (with auth)

**Recommended Fix:**
1. Document this behavior prominently in README
2. Add `--verify-ssl` flag (default: off for backward compat)
3. Warn when using auth over unverified SSL

---

### 10.2: No Input Validation on CLI site_dir
**File:** `doc_search/cli/commands.py`  
**Lines:** Various  
**Severity:** Low  
**Effort:** Quick Win

**Description:**
`get_site_dir()` accepts any string and uses it to construct paths:
```python
def get_site_dir(url_or_path: str, include_path: bool = False) -> Path:
    path = Path(url_or_path)
    if path.is_dir():
        return path
    return DEFAULT_DATA_DIR / site_hash(url_or_path, include_path=include_path)
```

**Why It's a Problem:**
- No validation that URL is actually a URL
- Could pass weird paths that work unexpectedly
- Minor concern (local tool, trusted input)

**Recommended Fix:**
Add basic validation:
```python
if not path.is_dir() and not url_or_path.startswith(('http://', 'https://')):
    raise ValueError(f"Expected URL or existing directory, got: {url_or_path}")
```

---

### Category 11: Missing Features (Future Consideration)

---

### 11.1: No Progress Callback During Crawl
**File:** `doc_search/crawler.py`  
**Severity:** Low  
**Effort:** Medium

**Description:**
Crawl progress is printed to stdout. No way to get progress programmatically.

**Why It's a Problem:**
- Can't build progress bars in GUIs
- Can't integrate with other systems
- Verbose output can't be suppressed while still tracking progress

**Recommended Fix:**
Add optional progress callback:
```python
def crawl(self, resume: bool = True, 
          progress_callback: Optional[Callable[[int, int], None]] = None):
    ...
    if progress_callback:
        progress_callback(pages_crawled, total_pending)
```

---

### 11.2: No Index Versioning
**File:** `doc_search/indexer.py`  
**Severity:** Low  
**Effort:** Medium

**Description:**
Index format has no version field. If format changes, old indexes silently break.

**Recommended Fix:**
Add version to saved index:
```python
data = {
    'version': 1,  # Increment on format changes
    'k1': self.k1,
    ...
}
```

---

## Quick Wins Summary (< 1 hour each)

| # | Issue | File | Impact |
|---|-------|------|--------|
| 4.1 | Add module docstrings | Multiple | Documentation |
| 5.1 | Extract auth header helper | utils.py | DRY |
| 5.2 | Extract SSL context helper | utils.py | DRY |
| 8.1 | Audit private method naming | Multiple | Clarity |
| 8.2 | Rename `stem` parameter | utils.py | Clarity |
| 9.1 | Add warning for skipped pages | crawler.py | Debuggability |
| 9.2 | Narrow exception handling | parser.py | Reliability |
| 10.1 | Document SSL behavior | README.md | Security |
| 10.2 | Validate CLI site_dir | commands.py | Robustness |

---

## Top 10 Refactoring Priorities

1. **Add CLI tests** (Issue 1.1, 1.2) - Highest risk area with 0% coverage
2. **Add integration tests** (Issue 1.3) - Verify full workflow
3. **Fix API inconsistency** (Issue 3.1) - SearchEngine return types
4. **Extract auth helpers** (Issue 5.1, 5.2) - Quick DRY wins
5. **Optimize pending URL dedup** (Issue 6.1) - Performance for large crawls
6. **Add index versioning** (Issue 11.2) - Future-proofing
7. **Document SSL behavior** (Issue 10.1) - Security transparency
8. **Add API documentation** (Issue 4.2) - Enable library usage
9. **Narrow exception handling** (Issue 9.2) - Reliability
10. **Add progress callback** (Issue 11.1) - Programmatic usage

---

## Incremental Refactor Plan

### Phase 1: Test Coverage (Priority: Critical)
**Estimated Time:** 2-3 days

1. Create `tests/test_cli.py` with mocked dependencies
2. Test all CLI commands with various inputs
3. Create `tests/test_integration.py` for end-to-end workflow
4. Achieve >80% coverage on CLI module

### Phase 2: Quick Wins (Priority: High)
**Estimated Time:** 1 day

1. Extract `make_basic_auth_header()` to utils
2. Extract `create_permissive_ssl_context()` to utils
3. Add module docstrings
4. Rename `stem` parameter to `apply_stemming`
5. Add warning for skipped JSON files
6. Narrow exception handling in parser

### Phase 3: API Cleanup (Priority: Medium)
**Estimated Time:** 1-2 days

1. Decide on SearchEngine/EnhancedSearchEngine return type strategy
2. Implement chosen approach
3. Update all callers
4. Add deprecation warning if needed

### Phase 4: Performance (Priority: Medium)
**Estimated Time:** 1 day

1. Optimize `CrawlState.add_urls()` with persistent set
2. Benchmark before/after with 10K+ URLs
3. Add performance test to prevent regression

### Phase 5: Documentation (Priority: Low)
**Estimated Time:** 1 day

1. Create `docs/API.md` with library usage guide
2. Expand `docs/ARCHITECTURE.md` with data flow
3. Document SSL certificate behavior in README
4. Add index format specification

### Phase 6: Large File Decomposition (Priority: Low)
**Estimated Time:** 2-3 days

1. Extract crawler fetcher module
2. Extract crawler URL filter module
3. Keep Crawler as orchestrator
4. Maintain backward compatibility
5. Update tests

---

## Metrics to Track

| Metric | Current | Target |
|--------|---------|--------|
| Test count | 459 | 550+ |
| CLI test coverage | 0% | 80%+ |
| Total code lines | 6,530 | ~7,000 (with tests) |
| Largest file | 833 (crawler.py) | <500 |
| Quick wins completed | 0 | 9 |

---

## Conclusion

The doc-search codebase is in good shape following the v1.9.0 refactor. The main gaps are:

1. **Test coverage for CLI** - Critical for maintenance confidence
2. **API consistency** - Important for library users
3. **Documentation** - Enables broader adoption

The codebase follows good practices:
- ✅ Type hints throughout
- ✅ Docstrings on most functions
- ✅ Thread-safe state management
- ✅ Graceful error handling
- ✅ Zero external dependencies

Recommended approach: Complete Phase 1 (tests) before other refactoring to establish a safety net for future changes.
