# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.17.0] - 2026-02-10

### Added
- **SymSpell fuzzy search** - Fast "Did you mean?" suggestions using Symmetric Delete algorithm (#185)
  - Enabled by default, use `--no-symspell` to disable
  - Pure Python implementation, no dependencies
- **N-gram prefix search** - Wildcard search with `*` suffix (e.g., `pyth*` → python, pythonic, ...)
  - Use `--no-ngram` to disable
  - Works on older indexes via fallback prefix matching
- **Wildcard highlighting** - Expanded terms are now highlighted in search result snippets

### Changed
- **2.6x faster snippet generation** - Optimized `find_best_snippet` for wildcard queries
  - Pre-lowercase words once instead of per-window
  - Only check windows around actual term matches

### Fixed
- Wildcard `*` character preserved in queries (was being stripped by tokenizer)
- Expanded terms now highlighted in snippets (was showing raw wildcard)

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
