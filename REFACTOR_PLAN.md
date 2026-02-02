# doc-search Incremental Refactor Plan

**Created:** 2026-02-02  
**Version Analyzed:** v1.8.2  
**Status:** Planning

---

## Phase 1: Quick Wins (Estimated: 1-2 days)

Small, low-risk improvements that deliver immediate value.

---

### Issue 1.1: Add LRU Cache to Stemmer

**Title:** Phase 1.1: Add LRU cache to `stem()` function for performance

**Description:**  
The `stem()` function in `stemmer.py` is called repeatedly on the same words during indexing and searching. Adding an LRU cache will avoid redundant computation.

**Tasks:**
- [ ] Import `functools.lru_cache`
- [ ] Add `@lru_cache(maxsize=10000)` decorator to `stem()` function
- [ ] Add test verifying cache behavior

**Completion Criteria:**
- `stem()` returns cached results for repeated calls
- Existing stemmer tests still pass
- No behavior change (pure performance improvement)

**Files:** `doc_search/stemmer.py`

---

### Issue 1.2: Add BM25 Parameter Validation

**Title:** Phase 1.2: Validate BM25 k1/b parameters in `BM25Index.__init__`

**Description:**  
Invalid BM25 parameters (e.g., `k1=-1`, `b=2.0`) are silently accepted and produce garbage results. Add validation with clear error messages.

**Tasks:**
- [ ] Add validation: `k1 >= 0`
- [ ] Add validation: `0 <= b <= 1`
- [ ] Raise `ValueError` with descriptive message on invalid input
- [ ] Add unit tests for validation

**Completion Criteria:**
- `BM25Index(k1=-1)` raises `ValueError`
- `BM25Index(b=1.5)` raises `ValueError`
- Valid parameters still work normally
- Tests cover edge cases (0, 1, negative, >1)

**Files:** `doc_search/indexer.py`, `tests/test_indexer.py` (new)

---

### Issue 1.3: Create Constants Module

**Title:** Phase 1.3: Extract magic numbers to `constants.py`

**Description:**  
Magic numbers are scattered throughout the codebase. Consolidate them into a single constants module for clarity and easier tuning.

**Tasks:**
- [ ] Create `doc_search/constants.py`
- [ ] Extract constants from `searcher.py`: `SNIPPET_LENGTH`, `SNIPPET_WINDOW_WORDS`, `PHRASE_MATCH_BONUS`
- [ ] Extract constants from `crawler.py`: `CHECKPOINT_INTERVAL`, `MAX_RETRIES`
- [ ] Extract constants from `spellcheck.py`: `DEFAULT_MAX_EDIT_DISTANCE`
- [ ] Update imports in affected modules
- [ ] Document each constant with a comment

**Completion Criteria:**
- All magic numbers centralized in `constants.py`
- Each constant has a descriptive name and comment
- All existing tests pass
- No behavior change

**Files:** `doc_search/constants.py` (new), `doc_search/searcher.py`, `doc_search/crawler.py`, `doc_search/spellcheck.py`

---

### Issue 1.4: Add Optional Server Request Logging

**Title:** Phase 1.4: Enable optional request logging in web server

**Description:**  
The web server silences all request logging, making debugging difficult. Add an optional flag to enable logging.

**Tasks:**
- [ ] Add `--log-requests` flag to `serve` command
- [ ] Pass flag to `SearchHandler` class
- [ ] Implement conditional logging in `log_message()`
- [ ] Log format: `[HH:MM:SS] GET /?q=query (200)`

**Completion Criteria:**
- `python -m doc_search serve site` — no logging (default)
- `python -m doc_search serve site --log-requests` — logs each request
- Log includes timestamp, method, path, status code

**Files:** `doc_search/__main__.py`, `doc_search/server.py`

---

### Issue 1.5: Add Accessor Methods to BM25Index

**Title:** Phase 1.5: Add public accessor methods to `BM25Index` class

**Description:**  
`SearchEngine` directly accesses internal `BM25Index` attributes (`url_to_id`, `documents`). Add proper accessor methods to establish a clean API boundary.

**Tasks:**
- [ ] Add `get_doc_id(url: str) -> Optional[int]`
- [ ] Add `get_document(doc_id: int) -> Optional[Dict]`
- [ ] Add `has_url(url: str) -> bool`
- [ ] Update `searcher.py` to use new methods
- [ ] Add tests for new methods

**Completion Criteria:**
- New methods exist and work correctly
- `SearchEngine` no longer accesses `index.url_to_id` directly
- All search tests pass

**Files:** `doc_search/indexer.py`, `doc_search/searcher.py`, `tests/test_search.py`

---

### Issue 1.6: Unify URL Hashing Functions

**Title:** Phase 1.6: Consolidate `url_to_filename` and `site_hash` functions

**Description:**  
Two similar hashing functions exist with different truncation lengths (16 vs 12). Unify into a single parameterized function.

**Tasks:**
- [ ] Create `hash_string(s: str, length: int = 16) -> str`
- [ ] Refactor `url_to_filename()` to use `hash_string(url, 16)`
- [ ] Refactor `site_hash()` to use `hash_string(key, 12)`
- [ ] Document why different lengths are used (if intentional)

**Completion Criteria:**
- Single source of truth for hashing logic
- Existing behavior unchanged
- All tests pass

**Files:** `doc_search/utils.py`

---

### Issue 1.7: Make Web UI Pagination Configurable

**Title:** Phase 1.7: Add CLI flags for web UI pagination settings

**Description:**  
Web UI pagination is hardcoded to 10 results per page and 100 max results. Make these configurable via CLI.

**Tasks:**
- [ ] Add `--per-page` flag to `serve` command (default: 10)
- [ ] Add `--max-results` flag to `serve` command (default: 100)
- [ ] Pass values to `SearchHandler`
- [ ] Validate: `per_page >= 1`, `max_results >= per_page`

**Completion Criteria:**
- `python -m doc_search serve site --per-page 20` works
- `python -m doc_search serve site --max-results 50` works
- Invalid values show helpful error message

**Files:** `doc_search/__main__.py`, `doc_search/server.py`

---

## Phase 2: Test Coverage (Estimated: 5-7 days)

Add tests for currently untested critical modules.

---

### Issue 2.1: Create Crawler Test File Structure

**Title:** Phase 2.1: Set up `test_crawler.py` with test fixtures

**Description:**  
Create the test file structure and shared fixtures for crawler tests.

**Tasks:**
- [ ] Create `tests/test_crawler.py`
- [ ] Create mock HTML responses fixture
- [ ] Create temporary directory fixture for crawl state
- [ ] Add helper to create test `Crawler` instances

**Completion Criteria:**
- Test file exists with working fixtures
- At least one placeholder test passes
- Can instantiate `Crawler` in tests without network calls

**Files:** `tests/test_crawler.py` (new)

---

### Issue 2.2: Add URL Filtering Tests

**Title:** Phase 2.2: Add tests for `Crawler._should_crawl()` method

**Description:**  
Test all URL filtering logic: extensions, depth, domain, path restrictions, robots.txt.

**Tasks:**
- [ ] Test: skips non-HTML extensions (`.zip`, `.png`, etc.)
- [ ] Test: respects `max_depth` limit
- [ ] Test: respects `same_path` restriction
- [ ] Test: respects `stay_on_domain` setting
- [ ] Test: skips download/archive paths
- [ ] Test: handles already-visited URLs

**Completion Criteria:**
- Each filtering rule has at least one positive and one negative test
- Edge cases covered (empty path, root path, trailing slashes)

**Files:** `tests/test_crawler.py`

---

### Issue 2.3: Add CrawlState Tests

**Title:** Phase 2.3: Add tests for `CrawlState` persistence and thread safety

**Description:**  
Test the crawl state management: saving, loading, thread-safe operations.

**Tasks:**
- [ ] Test: `save()` creates valid JSON file
- [ ] Test: `load()` restores state correctly
- [ ] Test: handles missing state file gracefully
- [ ] Test: handles corrupted state file gracefully
- [ ] Test: `mark_visited()` is thread-safe
- [ ] Test: `pop_url()` is thread-safe

**Completion Criteria:**
- State round-trips correctly (save → load → identical state)
- Concurrent access doesn't corrupt state
- Graceful handling of edge cases

**Files:** `tests/test_crawler.py`

---

### Issue 2.4: Add RateLimiter Tests

**Title:** Phase 2.4: Add tests for `RateLimiter` class

**Description:**  
Test rate limiting behavior: delays, backoff, per-domain tracking.

**Tasks:**
- [ ] Test: enforces minimum delay between requests
- [ ] Test: respects per-domain custom delays
- [ ] Test: handles backoff correctly
- [ ] Test: different domains don't block each other

**Completion Criteria:**
- Timing tests verify correct delays (with tolerance)
- Backoff resets after expiry
- Thread-safe delay enforcement

**Files:** `tests/test_crawler.py`

---

### Issue 2.5: Add Incremental Crawl Tests

**Title:** Phase 2.5: Add tests for incremental crawling logic

**Description:**  
Test the incremental crawl feature: detecting unchanged pages, using ETags/Last-Modified.

**Tasks:**
- [ ] Test: detects unchanged content via hash
- [ ] Test: uses ETag for conditional requests
- [ ] Test: uses Last-Modified for conditional requests
- [ ] Test: re-downloads changed pages
- [ ] Test: stats track unchanged vs updated pages

**Completion Criteria:**
- Incremental crawl correctly identifies changed vs unchanged
- HTTP 304 responses handled correctly
- Stats accurately reflect crawl results

**Files:** `tests/test_crawler.py`

---

### Issue 2.6: Create Server Test File

**Title:** Phase 2.6: Set up `test_server.py` with test client

**Description:**  
Create test infrastructure for the web server.

**Tasks:**
- [ ] Create `tests/test_server.py`
- [ ] Create helper to start/stop test server
- [ ] Create mock `SearchEngine` for testing
- [ ] Add helper to make HTTP requests to test server

**Completion Criteria:**
- Can start server in tests
- Can make requests without real index
- Server stops cleanly after tests

**Files:** `tests/test_server.py` (new)

---

### Issue 2.7: Add Server Response Tests

**Title:** Phase 2.7: Add tests for server HTTP responses

**Description:**  
Test the web server responses: HTML content, search results, pagination.

**Tasks:**
- [ ] Test: GET `/` returns welcome page
- [ ] Test: GET `/?q=test` returns search results
- [ ] Test: GET `/?q=test&page=2` returns paginated results
- [ ] Test: response includes correct Content-Type
- [ ] Test: HTML escapes user input (XSS prevention)

**Completion Criteria:**
- All response codes correct
- HTML is well-formed
- User input is escaped in output

**Files:** `tests/test_server.py`

---

### Issue 2.8: Create Robots.txt Tests

**Title:** Phase 2.8: Add tests for `RobotsChecker` class

**Description:**  
Test robots.txt parsing and compliance checking.

**Tasks:**
- [ ] Create `tests/test_robots.py`
- [ ] Test: allows all URLs when no robots.txt
- [ ] Test: respects Disallow rules
- [ ] Test: respects crawl-delay
- [ ] Test: handles malformed robots.txt gracefully

**Completion Criteria:**
- Correct Allow/Disallow behavior
- Crawl delay extracted correctly
- No crashes on malformed input

**Files:** `tests/test_robots.py` (new)

---

### Issue 2.9: Create PDF Extractor Tests

**Title:** Phase 2.9: Add tests for `PDFExtractor` class

**Description:**  
Test PDF text extraction functionality.

**Tasks:**
- [ ] Create `tests/test_pdf_extractor.py`
- [ ] Create small test PDF fixture
- [ ] Test: extracts text from valid PDF
- [ ] Test: extracts metadata (title, author)
- [ ] Test: handles empty PDF gracefully
- [ ] Test: handles corrupted PDF gracefully

**Completion Criteria:**
- Text extraction works on valid PDFs
- Metadata extraction works
- Graceful error handling for invalid PDFs

**Files:** `tests/test_pdf_extractor.py` (new), `tests/fixtures/test.pdf` (new)

---

## Phase 3: Module Extraction (Estimated: 3-5 days)

Improve code organization by extracting modules.

---

### Issue 3.1: Extract Searcher Utilities

**Title:** Phase 3.1: Extract formatting functions from `searcher.py`

**Description:**  
Move formatting and highlighting functions to a separate module to reduce file size and improve organization.

**Tasks:**
- [ ] Create `doc_search/searcher_utils.py`
- [ ] Move `format_results()` function
- [ ] Move `highlight_terms()` function
- [ ] Move `highlight_terms_ansi()` function
- [ ] Move `find_best_snippet()` function
- [ ] Update imports in `searcher.py`

**Completion Criteria:**
- `searcher.py` is smaller and focused on search logic
- `searcher_utils.py` contains all formatting code
- All tests pass, no behavior change

**Files:** `doc_search/searcher_utils.py` (new), `doc_search/searcher.py`

---

### Issue 3.2: Extract CrawlState to Separate Module

**Title:** Phase 3.2: Extract `CrawlState` class from `crawler.py`

**Description:**  
Move the `CrawlState` class to its own module for better organization and testability.

**Tasks:**
- [ ] Create `doc_search/crawl_state.py`
- [ ] Move `CrawlState` class
- [ ] Update imports in `crawler.py`
- [ ] Ensure all crawler tests still pass

**Completion Criteria:**
- `CrawlState` is in its own module
- `crawler.py` imports from `crawl_state.py`
- No behavior change

**Files:** `doc_search/crawl_state.py` (new), `doc_search/crawler.py`

---

### Issue 3.3: Extract RateLimiter to Separate Module

**Title:** Phase 3.3: Extract `RateLimiter` class from `crawler.py`

**Description:**  
Move the `RateLimiter` class to its own module.

**Tasks:**
- [ ] Create `doc_search/rate_limiter.py`
- [ ] Move `RateLimiter` class
- [ ] Update imports in `crawler.py`
- [ ] Ensure all tests pass

**Completion Criteria:**
- `RateLimiter` is in its own module
- Can be imported and tested independently
- No behavior change

**Files:** `doc_search/rate_limiter.py` (new), `doc_search/crawler.py`

---

### Issue 3.4: Create CLI Package Structure

**Title:** Phase 3.4: Convert `__main__.py` to CLI package

**Description:**  
Extract CLI logic into a package for better organization.

**Tasks:**
- [ ] Create `doc_search/cli/` directory
- [ ] Create `doc_search/cli/__init__.py` with `main()` function
- [ ] Create `doc_search/cli/commands.py` for command implementations
- [ ] Create `doc_search/cli/parsers.py` for argument parsing
- [ ] Update `__main__.py` to import from CLI package
- [ ] Ensure all CLI functionality works

**Completion Criteria:**
- CLI package structure exists
- `python -m doc_search` still works
- Each command is a separate function in `commands.py`
- Argument definitions are in `parsers.py`

**Files:** `doc_search/cli/` (new package), `doc_search/__main__.py`

---

### Issue 3.5: Extract CLI Command Functions

**Title:** Phase 3.5: Move command functions to `cli/commands.py`

**Description:**  
Move all `cmd_*` functions from `__main__.py` to the commands module.

**Tasks:**
- [ ] Move `cmd_crawl()` to `commands.py`
- [ ] Move `cmd_index()` to `commands.py`
- [ ] Move `cmd_search()` to `commands.py`
- [ ] Move `cmd_interactive()` to `commands.py`
- [ ] Move `cmd_serve()` to `commands.py`
- [ ] Move `cmd_stats()` to `commands.py`
- [ ] Move `cmd_list()` to `commands.py`
- [ ] Move `cmd_autocomplete()` to `commands.py`
- [ ] Update imports

**Completion Criteria:**
- All commands work as before
- `__main__.py` is minimal (just imports and calls `main()`)
- Commands are independently testable

**Files:** `doc_search/cli/commands.py`, `doc_search/__main__.py`

---

## Phase 4: Error Handling & Observability (Estimated: 2-3 days)

Improve debugging and error tracking capabilities.

---

### Issue 4.1: Create CrawlError Data Class

**Title:** Phase 4.1: Add structured error tracking for crawler

**Description:**  
Create a data class for crawl errors to enable better tracking and debugging.

**Tasks:**
- [ ] Create `CrawlError` dataclass with: `url`, `error_type`, `message`, `timestamp`
- [ ] Add `errors: List[CrawlError]` to `CrawlState`
- [ ] Update `CrawlState.save()` to persist errors
- [ ] Update `CrawlState.load()` to restore errors

**Completion Criteria:**
- Errors can be recorded with full context
- Errors persist across crawl resumption
- Errors are serializable to JSON

**Files:** `doc_search/crawler.py` (or `doc_search/crawl_state.py`)

---

### Issue 4.2: Record Errors During Crawl

**Title:** Phase 4.2: Update crawler to record errors using `CrawlError`

**Description:**  
Replace ad-hoc error handling with structured error recording.

**Tasks:**
- [ ] Record HTTP errors with status code
- [ ] Record timeout errors
- [ ] Record parse errors
- [ ] Record SSL errors
- [ ] Add `get_errors()` method to return error summary

**Completion Criteria:**
- All error types are captured
- Error count matches `pages_failed` stat
- Errors include enough context to debug

**Files:** `doc_search/crawler.py`

---

### Issue 4.3: Add Error Summary to Stats Command

**Title:** Phase 4.3: Show error summary in `stats` command output

**Description:**  
Display crawl error information when running `doc_search stats`.

**Tasks:**
- [ ] Load errors from crawl state
- [ ] Group errors by type
- [ ] Display error type counts
- [ ] Optionally show recent error URLs (`--show-errors`)

**Completion Criteria:**
- `stats` command shows error summary
- `stats --show-errors` shows detailed error list
- Helps users debug crawl issues

**Files:** `doc_search/__main__.py` (or `doc_search/cli/commands.py`)

---

### Issue 4.4: Add Health Check Endpoint

**Title:** Phase 4.4: Add `/health` endpoint to web server

**Description:**  
Add a health check endpoint for monitoring and load balancers.

**Tasks:**
- [ ] Add route for `GET /health`
- [ ] Return JSON: `{"status": "ok", "documents": N, "terms": N}`
- [ ] Include uptime in response
- [ ] Return 200 for healthy, 503 for unhealthy

**Completion Criteria:**
- `/health` returns valid JSON
- Response includes useful metrics
- Can be used by monitoring systems

**Files:** `doc_search/server.py`

---

## Phase 5: Documentation & Polish (Estimated: 1-2 days)

Final cleanup and documentation.

---

### Issue 5.1: Add CHANGELOG.md

**Title:** Phase 5.1: Create CHANGELOG.md with version history

**Description:**  
Document all releases and changes for users.

**Tasks:**
- [ ] Create `CHANGELOG.md`
- [ ] Document v1.8.x changes
- [ ] Document v1.7.x changes
- [ ] Follow Keep a Changelog format

**Completion Criteria:**
- CHANGELOG exists with all versions
- Each version lists Added/Changed/Fixed/Removed
- Links to relevant PRs/issues

**Files:** `CHANGELOG.md` (new)

---

### Issue 5.2: Document Tokenization Behavior

**Title:** Phase 5.2: Add documentation for tokenization behavior

**Description:**  
Document what gets filtered during tokenization (stopwords, short words).

**Tasks:**
- [ ] Add docstring to `tokenize()` explaining filtering
- [ ] List all stopwords in documentation
- [ ] Explain single-letter word filtering
- [ ] Add examples to README or separate doc

**Completion Criteria:**
- Users understand what gets indexed
- Behavior is documented, not surprising

**Files:** `doc_search/utils.py`, `README.md` or `docs/`

---

### Issue 5.3: Add Architecture Documentation

**Title:** Phase 5.3: Create architecture overview documentation

**Description:**  
Add high-level documentation explaining module relationships.

**Tasks:**
- [ ] Create `docs/ARCHITECTURE.md`
- [ ] Document module responsibilities
- [ ] Show data flow: crawl → index → search
- [ ] Include simple ASCII diagram

**Completion Criteria:**
- New contributors can understand codebase structure
- Module purposes are clear
- Data flow is documented

**Files:** `docs/ARCHITECTURE.md` (new)

---

### Issue 5.4: Add Type Hints to Stemmer

**Title:** Phase 5.4: Add complete type hints to `stemmer.py`

**Description:**  
Add type hints to all functions in the stemmer module.

**Tasks:**
- [ ] Add type hints to all public functions
- [ ] Add type hints to internal helper functions
- [ ] Verify with `mypy` (optional)

**Completion Criteria:**
- All functions have parameter and return type hints
- IDE provides accurate autocompletion

**Files:** `doc_search/stemmer.py`

---

### Issue 5.5: Add Type Hints to Parser

**Title:** Phase 5.5: Add complete type hints to `parser.py`

**Description:**  
Add type hints to all functions in the parser module.

**Tasks:**
- [ ] Add type hints to `HTMLTextExtractor` methods
- [ ] Add type hints to `extract_text()`
- [ ] Add type hints to `extract_links()`

**Completion Criteria:**
- All functions have complete type hints
- IDE provides accurate autocompletion

**Files:** `doc_search/parser.py`

---

## Summary

| Phase | Issues | Estimated Time |
|-------|--------|----------------|
| Phase 1: Quick Wins | 7 | 1-2 days |
| Phase 2: Test Coverage | 9 | 5-7 days |
| Phase 3: Module Extraction | 5 | 3-5 days |
| Phase 4: Error Handling | 4 | 2-3 days |
| Phase 5: Documentation | 5 | 1-2 days |
| **Total** | **30** | **12-19 days** |

---

## Getting Started

1. Start with **Phase 1** — quick wins build momentum
2. **Phase 2** can run in parallel with other phases
3. **Phase 3** depends on Phase 2 tests being in place
4. **Phase 4** and **Phase 5** can be done anytime

Each issue is independently completable. Pick any issue with satisfied dependencies and start!
