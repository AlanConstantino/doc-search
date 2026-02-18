# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.26.0] - 2026-02-18

### Added
- **Suggest-as-you-type in web UI** — dropdown with autocomplete suggestions as you type (2+ chars), prefix highlighted, keyboard navigable (↑/↓/Enter/Escape), click to select
- **Tab completion in interactive terminal** — press Tab to autocomplete search terms from the index vocabulary
- **Doc type breakdown in crawl/index summaries** — shows PDFs, Word docs, Excel sheets extracted at end of crawl
- **Informative checkpoint messages** — progress summary with pages, docs, queue, MB, rate

### Fixed
- **BrokenPipeError suppressed** — no more noisy tracebacks when browser aborts search requests (instant search typing)
- **PDF snippet formatting in terminal** — aggressively joins broken lines, collapses newlines for clean single-line display
- **Cleaner list format** — `(51 pages: 45 html, 6 pdf)` instead of nested parens

### Changed
- List command uses cached `doc_type_counts` from metadata (~40x faster for large sites)
- `--refresh` flag on list to rebuild cache when needed

## [1.25.0] - 2026-02-18

### Added
- **Doc type badges in interactive terminal** — all search results now show `[WEB]`, `[PDF]`, `[DOCX]`, or `[XLSX]` badges, color-coded (red/green/blue/dim)
- **File serving endpoint** (`/files/`) — local documents (PDF, Word, Excel) can now be opened from the web UI; browsers previously blocked `file://` URLs
- **Text normalization for PDF/Word snippets** — `normalize_document_text()` cleans up extraction artifacts (broken lines, soft hyphens, unicode whitespace) for better snippet display
- **Content type indicators in crawl logs** — emojis show what's being processed: 🌐 web, 📄 PDF, 📝 Word, 📊 Excel
- **Informative checkpoint messages** — replaces bare "Saving checkpoint..." with progress summary (pages, docs, queue, MB, rate)
- Updated `:type` filter to accept all document types with aliases (`web`, `word`, `excel`)

### Fixed
- File preview links in web UI now open correctly (PDF inline, Word/Excel download)
- PDF and Word document snippets are now properly formatted in both web UI and terminal

## [1.24.0] - 2026-02-17

### Fixed
- Fix `KeyError: 'unique_terms'` crash when serving in multi-site mode (`--all`)
- Use `.get()` with fallback for stats keys across `cmd_serve`, `cmd_stats`, server footer, and `/health` endpoint

### Removed
- Levenshtein automaton module and all integrations (1,569 lines removed)
- Two-pass fuzzy fallback search architecture
- `docs/SEARCH_ARCHITECTURE.md`

## [1.23.0] - 2026-02-17

### Added
- **Multi-site search** (#144)
  - New `search-all` CLI command to search across all crawled sites simultaneously
  - Results merged and ranked by BM25 score across sites
  - Each result annotated with source site
  - `--sites` flag to filter specific sites by URL, name, or hash prefix
  - `--all` flag on `serve` command for multi-site web UI
  - JSON output support via `--json` flag
  - New `multi_search.py` module with `MultiSiteSearchEngine` class

- **Incremental index updates** (#141)
  - Re-indexing only processes new/changed/deleted pages instead of full rebuild
  - Content hashes (SHA-256) tracked per page for change detection
  - Stats output: "X new, Y updated, Z removed, W unchanged"
  - `--full` flag to force complete rebuild
  - `remove_document()` method on `BM25Index` for targeted removal
  - Content hashes persist across save/load cycles

## [1.22.0] - 2026-02-16

### Added
- **Page-based PDF chunking** for better search granularity (#205, #206)
  - Each PDF page indexed as a separate document
  - URLs include `#page=N` fragment for direct page linking
  - Titles show `{Document Title} - Page {N}` format
  - Metadata includes: page, total_pages, source_file, parent_title
  - Headings detected per-page for field-aware ranking
  - Better BM25 ranking (smaller documents = more accurate scoring)

### Changed
- `index-files` CLI now uses page-based extraction for PDFs
- A 50-page PDF creates 50 indexed documents (instead of 1)

## [1.21.1] - 2026-02-11

### Fixed
- **Security**: Replace MD5 with SHA256 in `index-files` command
  - Directory hash now uses SHA256
  - Document ID hash now uses SHA256
  - MD5 is cryptographically broken; SHA256 is the secure standard

## [1.21.0] - 2026-02-11

### Added

- **SymSpell "Did you mean?" suggestions**
  - Generated before search, displayed for user to click
  - Does NOT auto-execute - preserves user intent
  - Works in web UI and CLI

- **New configuration constants**
  - `MIN_RESULTS_FOR_FUZZY_FALLBACK = 5`
  - `FUZZY_MIN_TERM_LENGTH = 4`
  - `FUZZY_MAX_EXPANSIONS = 5`
  - `FUZZY_MAX_DISTANCE_SHORT = 1` (4-6 char terms)
  - `FUZZY_MAX_DISTANCE_LONG = 2` (7+ char terms)

- **Documentation**: `docs/SEARCH_ARCHITECTURE.md` with full flow diagram

### Changed
- Term weights updated: fuzzy dist 1 → 0.35 (was 0.5), dist 2 → 0.15 (was 0.3)
- Web UI and API now use `last_suggestion` from search engine

## [1.20.0] - 2026-02-11

### Added
- **Word (.docx) document support** (#202, #204)
  - Pure Python implementation using stdlib (zipfile + xml.etree.ElementTree)
  - Zero external dependencies
  - Heading detection from Word styles (Heading 1, 2, 3, Title, Subtitle)
  - Document properties extraction (title, author, created/modified dates)
  - Headers and footers included in extracted text
  - Word count calculation
  - Blue DOCX badge in web UI search results
  - Default extensions for `index-files` now: `xlsx,docx`

### Usage
```bash
# Index Word and Excel files
python -m doc_search index-files ./documents/

# Or just Word files
python -m doc_search index-files ./documents/ --extensions docx
```

### Note
Only .docx (Office 2007+) supported. For legacy .doc files:
```bash
libreoffice --headless --convert-to docx *.doc
```

## [1.19.0] - 2026-02-11

### Added
- **Excel (.xlsx) document support** (#201, #203)
  - New `index-files` command to index local Excel documents
  - One searchable document per worksheet
  - Header row detection for contextual text extraction
  - Text formatted as `Header: value, Header: value`
  - Configurable `--max-rows` limit for large files
  - Green XLSX badge in web UI search results
  - Type filter in web UI when site has multiple doc types
  - Vendored openpyxl 3.1.2 and et_xmlfile 2.0.0 (MIT license)

### Usage
```bash
# Index Excel files
python -m doc_search index-files ./documents/ --extensions xlsx

# Build search index
python -m doc_search index ~/.doc_search/sites/files_<hash>

# Search
python -m doc_search search ~/.doc_search/sites/files_<hash> "query"

# Web UI
python -m doc_search serve ~/.doc_search/sites/files_<hash> --open
```

## [1.18.0] - 2026-02-11

### ⚠️ BREAKING CHANGES
- **Python 3.9+ now required** (previously 3.7+) - needed for pypdf library

### Added
- **Enhanced PDF extraction with heading detection** (#198, #199)
  - Upgraded from PyPDF2 to pypdf for font-aware text extraction
  - Detects headings via font size, bold fonts, ALL CAPS, and numbered sections
  - Extracts PDF outline/TOC as additional headings
  - Headings used for field-aware search ranking (headings weighted 2-3x higher)

## [1.17.0] - 2026-02-11

### Added
- **Two-stage retrieval with reranking** (#190)
  - BM25 retrieval followed by feature-based reranking
  - Configurable via `RerankConfig`
- **Field-aware ranking** (#188)
  - Title matches: 5x weight
  - Heading matches: 2.5x weight
  - Body matches: 1x weight
- **Query term coverage boosting** (#191)
  - Results containing more query terms ranked higher
- **Phrase proximity boosting** (#189)
  - Results with query terms closer together ranked higher
- **Weighted term expansion** (#187)
  - Synonym and fuzzy matches weighted lower than exact matches
- **SymSpell fuzzy search** - Fast "Did you mean?" suggestions using Symmetric Delete algorithm (#185)
  - Enabled by default, use `--no-symspell` to disable
  - Pure Python implementation, no dependencies
- **N-gram prefix search** - Wildcard search with `*` suffix (e.g., `pyth*` → python, pythonic, ...)
  - Use `--no-ngram` to disable
  - Works on older indexes via fallback prefix matching
- **Wildcard highlighting** - Expanded terms are now highlighted in search result snippets

### Changed
- **2.6x faster snippet generation** - Optimized `find_best_snippet` for wildcard queries

### Fixed
- RerankMetrics JSON serialization for web UI cache
- Wildcard `*` character preserved in queries (was being stripped by tokenizer)
- Expanded terms now highlighted in snippets

## [1.16.1] - 2026-02-10

### Added
- **Delete command** - Remove crawled sites and their indexes (#184)
  - Delete by URL: `doc_search delete https://example.com`
  - Delete by hash ID: `doc_search delete abc123`
  - Delete all sites: `doc_search delete --all`
  - Preview mode: `doc_search delete --dry-run` shows what would be deleted without removing anything

## [1.16.0] - 2026-02-05

### Added
- **Interactive mode command history** - Use ↑/↓ arrow keys to cycle through previous commands (#183)
- History persists across sessions (stored in `.history` file per site)
- Keeps last 100 commands

## [1.15.0] - 2026-02-05

### Added
- **Instant search** - Results update as you type with 200ms debounce (#172, #173)
- **Search history** - Last 10 searches stored in localStorage (#174)
- **Keyboard navigation** - ↑/↓ to navigate results, Enter to open, Escape to close (#175)
- **Infinite scroll** - Automatically loads more results as you scroll (#176)
- **Result previews** - Expandable content snippets (#177)
- **Faceted filtering** - Filter by category with live counts (#178)
- **Search within results** - Cmd+F overlay to highlight matching text (#179)
- **Dark/light mode toggle** - iOS-style theme switcher (#180)
- **Copy link button** - Quick copy result URLs to clipboard
- **/api/search endpoint** - JSON API for programmatic access

### Changed
- Fixed overlay search bar at top of screen
- Hide "Results" dropdown when JavaScript is enabled

## [1.14.2] - 2026-02-04

### Added
- **`--no-javascript` flag** for serve command - Serve pure HTML/CSS UI without JS enhancements

### Fixed
- Improved `--password` help text for special characters (use single quotes for `$`)

## [1.14.1] - 2026-02-04

### Fixed
- Added `-b` and `-k` short options for index command (previously only `--b` and `--k1` worked)

## [1.14.0] - 2026-02-04

### Added
- **Search result caching** - LRU cache with configurable TTL (#142)
- **Persistent cache** - SQLite-based cache at `<site_dir>/.cache.db` (enabled by default)
- **Auto-invalidation** - Cache clears automatically when index is rebuilt (mtime-based)
- **Interactive mode pagination** - Navigate results with `[n]ext`/`[p]rev` commands
- **Interactive mode caching** - Search results cached for faster repeat queries

## [1.13.1] - 2026-02-04

### Added
- **`--ignore-robots` flag** - Skip robots.txt rules when crawling (use responsibly)

### Fixed
- **Thread safety in multi-worker crawling** - Fixed race condition in `CrawlState.save()` that could cause `RuntimeError: dictionary changed size during iteration` when using `--workers` flag (#170)

## [1.13.0] - 2026-02-03

### Added
- **DOM tree parser** - New default HTML parser with structure-aware content extraction (#168)
- **`--parser` flag** - Choose between `dom` (default) or `stream` (legacy) parser
- **Better boilerplate detection** - Strips content by tag, ARIA role, and CSS class patterns
- **Main content detection** - Finds `<main>`, `<article>`, or best-scoring content `<div>`
- **Re-parsing support** - Re-index with different parser using saved raw HTML

### Changed
- DOM parser is now the default (use `--parser=stream` for legacy behavior)
- Index command re-parses from raw HTML when available

## [1.12.1] - 2026-02-03

### Added
- **Raw HTML storage** - Crawler now saves raw HTML by default for re-parsing later (#167)
- **`--no-save-html` flag** - Disable raw HTML storage to save disk space
- **Keyboard shortcut** - `accesskey="s"` to focus search (Alt+S / Ctrl+Opt+S) (#161)
- **First/Last pagination** - Jump to beginning/end of results (#161)
- **Colored score bars** - Visual confidence indicators (green/yellow/red) with percentages (#163)

### Changed
- Exact match toggle now uses phrase matching (words must appear in order) (#164)
- Removed collapsible snippet cards for simpler UI (#160)
- Score bars normalize relative to global max score across all pages (#162)

### Fixed
- Search clear button (X) now positioned at right edge of input (#165)
- Score bar fill now displays correctly (#162)

## [1.12.0] - 2026-02-03

### Added
- **Web UI: Spell check suggestions** - "Did you mean..." appears when no results found (#149)
- **Web UI: Autocomplete** - `/suggest` endpoint for search suggestions (#150)
- **Web UI: Faceted search** - Filter results by category/section (#151)
- **Web UI: Search options** - Sort, results per page, exact match, theme toggle (#158)
- **`DOC_SEARCH_NO_EMOJI` env var** - ASCII fallbacks for systems without emoji fonts

### Changed
- Theme toggle now uses 🌙/☀️ link buttons instead of dropdown (no JavaScript)
- Web server now uses `EnhancedSearchEngine` (enables spellcheck, autocomplete, facets)
- Removed synonym toggle checkbox from UI (now CLI-flag only via `--synonyms`)

### Fixed
- Theme toggle works instantly (was requiring form submission)
- Exact match checkbox now properly disables synonym expansion
- Spellcheck suggestions now appear in web UI (was missing due to wrong engine class)

## [1.11.1] - 2026-02-02

### Fixed
- Documentation updates and minor fixes

## [1.11.0] - 2026-02-02

### Added
- LRU cache for stemmer function (10,000 word cache)
- BM25 parameter validation (`k1 >= 0`, `0 <= b <= 1`)
- Constants module for centralized configuration
- `--log-requests` flag for server request logging
- `--per-page` and `--max-results` flags for web UI pagination
- Accessor methods on `BM25Index` (`get_doc_id`, `get_document`, `has_url`)
- `hash_string()` utility function for unified hashing
- `/health` endpoint for server monitoring
- Structured error tracking with `CrawlError` dataclass
- Error summary in `stats` command (`--show-errors` for details)
- Comprehensive test coverage (955 tests)
  - CLI command tests for all commands
  - CLI parser tests
  - Integration tests (crawl → index → search workflow)
  - Full crawler package test coverage

### Changed
- Extracted `CrawlState` to `crawl_state.py`
- Extracted `RateLimiter` to `rate_limiter.py`
- Extracted formatting functions to `searcher_utils.py`
- CLI refactored into `cli/` package structure
- **Crawler refactored into `crawler/` package** (Phases 1-6.5):
  - `Fetcher` class for HTTP fetching with retry logic
  - `UrlFilter` class for URL validation and filtering
  - `PageProcessor` class for content processing
  - All public APIs preserved for backward compatibility
  - `from doc_search.crawler import Crawler, RateLimiter` still works

## [1.8.2] - 2024-02-02

### Added
- `--same-path` flag to bash scripts
- Clear validation output for crawl scope

### Fixed
- Incremental crawl now properly re-checks existing pages
- Handle `concurrent.futures.TimeoutError` for Python 3.9 compatibility

## [1.8.1] - 2024-02-01

### Changed
- Default to crawling entire domain (`same_path=False`)

### Fixed
- Crawl scope behavior now matches user expectations

## [1.8.0] - 2024-02-01

### Added
- PDF text extraction support via vendored PyPDF2
- Convenience bash scripts (`scripts/crawl.sh`, `scripts/serve.sh`)
- `--separate-paths` flag for per-path storage
- `--extract-docs` flag for PDF extraction during crawl

### Fixed
- Three edge case bugs with comprehensive tests

## [1.7.1] - 2024-01-31

### Changed
- Updated README with analysis report

## [1.7.0] - 2024-01-31

### Added
- Pagination support in web UI

## [1.6.0] - 2024-01-31

### Added
- Spell check suggestions ("Did you mean...")
- Autocomplete / type-ahead suggestions
- Faceted search (filter by URL path categories)
- Synonym expansion support

## [1.3.1] - 2024-01-30

### Added
- `--token` option for pre-encoded Base64 authentication

### Fixed
- Version parameter in `run_server` function

## [1.3.0] - 2024-01-30

### Added
- Beautiful web UI with pure HTML/CSS (no JavaScript required)
- Colorful CLI output with ANSI colors
- Result highlighting in terminal

### Changed
- Removed mobile breakpoints (desktop-focused experience)

## [1.2.0] - 2024-01-30

### Added
- Snippet highlighting with matched terms
- Phrase search with quoted strings (`"exact phrase"`)
- Parallel crawling with `--workers` option

## [1.1.0] - 2024-01-30

### Added
- `--same-path` option for path-restricted crawling
- `--max-depth` option for depth limiting
- Skip non-HTML files (PDFs, images, etc.)

## [1.0.0] - 2024-01-30

### Added
- Initial release
- Web crawler with robots.txt support
- BM25 search index
- Command-line interface
- Basic web server for search UI

[Unreleased]: https://github.com/AlanConstantino/doc-search/compare/v1.8.2...HEAD
[1.8.2]: https://github.com/AlanConstantino/doc-search/compare/v1.8.1...v1.8.2
[1.8.1]: https://github.com/AlanConstantino/doc-search/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/AlanConstantino/doc-search/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/AlanConstantino/doc-search/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/AlanConstantino/doc-search/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/AlanConstantino/doc-search/compare/v1.3.1...v1.6.0
[1.3.1]: https://github.com/AlanConstantino/doc-search/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/AlanConstantino/doc-search/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/AlanConstantino/doc-search/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/AlanConstantino/doc-search/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/AlanConstantino/doc-search/releases/tag/v1.0.0
