# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
