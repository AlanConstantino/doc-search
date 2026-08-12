"""
Argument parsers for doc-search CLI commands.

This module defines all CLI argument parsers and their options.
"""

import argparse
from .. import __version__
from .commands import (
    cmd_crawl, cmd_index, cmd_index_files, cmd_search, cmd_search_all,
    cmd_autocomplete, cmd_interactive, cmd_stats, cmd_list, cmd_delete, cmd_serve
)


def create_parser() -> argparse.ArgumentParser:
    """Create and return the main argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog='doc_search',
        description='Search through documentation websites and local files (PDF, DOCX, XLSX, PPTX, HTML).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Crawl a documentation site (stays under /3.11/ path by default)
  python -m doc_search crawl https://docs.python.org/3.11/
  
  # Crawl with page limit and depth limit
  python -m doc_search crawl https://docs.python.org/3.11/ --max-pages 500 --max-depth 5
  
  # Restrict to starting path only
  python -m doc_search crawl https://docs.example.com/guide/ --same-path
  
  # Crawl with authentication
  python -m doc_search crawl https://docs.example.com --user admin
  
  # Build search index
  python -m doc_search index https://docs.python.org/3.11/
  
  # Search the index
  python -m doc_search search https://docs.python.org/3.11/ "list comprehension"
  
  # Interactive search mode
  python -m doc_search interactive https://docs.python.org/3.11/
"""
    )
    
    parser.add_argument('--version', action='version', version=f'doc_search {__version__}')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Add all command parsers
    _add_crawl_parser(subparsers)
    _add_index_parser(subparsers)
    _add_index_files_parser(subparsers)
    _add_search_parser(subparsers)
    _add_search_all_parser(subparsers)
    _add_autocomplete_parser(subparsers)
    _add_interactive_parser(subparsers)
    _add_stats_parser(subparsers)
    _add_list_parser(subparsers)
    _add_delete_parser(subparsers)
    _add_serve_parser(subparsers)
    
    return parser


def _add_crawl_parser(subparsers):
    """Add the crawl command parser."""
    crawl_parser = subparsers.add_parser('crawl', help='Crawl a documentation site')
    crawl_parser.add_argument('url', help='Base URL to crawl')
    crawl_parser.add_argument('--user', '-u', help='Username for HTTP Basic Auth')
    crawl_parser.add_argument('--password', '-p', help="Password (will prompt securely if not provided). Use single quotes for special chars: --password 'my$pass'")
    crawl_parser.add_argument('--token', help='Pre-encoded Base64 auth token (alternative to user/password)')
    crawl_parser.add_argument('--delay', '-d', type=float, default=1.0,
                             help='Delay between requests in seconds (default: 1.0)')
    crawl_parser.add_argument('--timeout', '-t', type=float, default=30.0,
                             help='Request timeout in seconds (default: 30)')
    crawl_parser.add_argument('--max-pages', '-m', type=int,
                             help='Maximum number of pages to crawl')
    crawl_parser.add_argument('--max-depth', type=int,
                             help='Maximum link depth from starting URL')
    crawl_parser.add_argument('--same-path', action='store_true',
                             help='Only crawl URLs under the starting path (default: crawl entire domain)')
    crawl_parser.add_argument('--ignore-robots', action='store_true',
                             help='Ignore robots.txt rules (use responsibly)')
    crawl_parser.add_argument('--fresh', '-f', action='store_true',
                             help='Start fresh crawl (ignore saved state)')
    crawl_parser.add_argument('--incremental', '-i', action='store_true',
                             help='Only re-download pages that have changed since last crawl')
    crawl_parser.add_argument('--workers', '-w', type=int, default=1,
                             help='Number of parallel workers (default: 1 for politeness)')
    crawl_parser.add_argument('--extract-docs', action='store_true',
                             help='Extract text from PDFs and Office documents')
    crawl_parser.add_argument('--no-save-html', action='store_true',
                             help='Do not save raw HTML (saves disk space but prevents re-parsing)')
    crawl_parser.add_argument('--parser', choices=['dom', 'stream'], default='dom',
                             help='HTML parser for text extraction: dom (default, better content detection) or stream (legacy)')
    crawl_parser.add_argument('--separate-paths', action='store_true',
                             help='Store different URL paths separately (e.g., /3.11/ and /3.12/ get their own folders)')
    crawl_parser.add_argument('--max-age', type=int, default=None, metavar='DAYS',
                             help='Re-crawl pages older than DAYS days')
    crawl_parser.add_argument('--quiet', '-q', action='store_true',
                             help='Suppress progress output')
    crawl_parser.set_defaults(func=cmd_crawl)


def _add_index_parser(subparsers):
    """Add the index command parser."""
    index_parser = subparsers.add_parser('index', help='Build search index')
    index_parser.add_argument('site_dir', help='Site data directory or original URL')
    index_parser.add_argument('--k1', '-k', type=float, default=1.5,
                             help='BM25 k1 parameter (default: 1.5)')
    index_parser.add_argument('--b', '-b', type=float, default=0.75,
                             help='BM25 b parameter (default: 0.75)')
    index_parser.add_argument('--no-compress', action='store_true',
                             help='Don\'t compress the index file')
    index_parser.add_argument('--no-stemming', action='store_true',
                             help='Disable Porter stemming')
    index_parser.add_argument('--no-symspell', action='store_true',
                             help='Skip building SymSpell index for suggestions')
    index_parser.add_argument('--no-ngram', action='store_true',
                             help='Skip building n-gram index for prefix/substring search')
    index_parser.add_argument('--separate-paths', action='store_true',
                             help='Use if site was crawled with --separate-paths')
    index_parser.add_argument('--parser', choices=['dom', 'stream'], default='dom',
                             help='HTML parser used only with --reparse (default: dom)')
    index_parser.add_argument('--reparse', action='store_true',
                             help='Re-extract text from saved raw_html (default: trust crawl-time text)')
    index_parser.add_argument('--chunks', action='store_true',
                             help='Index heading sections as separate anchor docs (off by default)')
    index_parser.add_argument('--max-body-chars', type=int, default=200000,
                             help='Max body characters to analyze per doc (default: 200000)')
    index_parser.add_argument('--no-url-filter', action='store_true',
                             help='Do not skip genindex/search/changelog-style URLs')
    index_parser.add_argument('--full', action='store_true',
                             help='Force a complete rebuild (skip incremental)')
    index_parser.add_argument('--no-suggestions', action='store_true',
                             help='Skip building content suggestion index')
    index_parser.add_argument('--suggest-max-words', type=int, default=3,
                             help='Maximum words per suggestion phrase (default: 3, min: 1)')
    index_parser.add_argument('--quiet', '-q', action='store_true',
                             help='Suppress progress output')
    index_parser.set_defaults(func=cmd_index)


def _add_index_files_parser(subparsers):
    """Add the index-files command parser for local documents."""
    index_files_parser = subparsers.add_parser(
        'index-files', 
        help='Index local documents (.pdf, .docx, .xlsx, .pptx, .html)'
    )
    index_files_parser.add_argument('directory', help='Directory containing files to index')
    index_files_parser.add_argument('--extensions', '-e', default='xlsx,docx,pdf,pptx,html,htm',
                                    help='Comma-separated file extensions to include (default: xlsx,docx,pdf,pptx,html,htm)')
    index_files_parser.add_argument('--no-recursive', action='store_true',
                                    help='Do not scan subdirectories (default: recursive)')
    index_files_parser.add_argument('--exclude', action='append', metavar='PATTERN',
                                    help='Glob pattern to exclude (can be repeated)')
    index_files_parser.add_argument('--site-name', metavar='NAME',
                                    help='Name for this document set (default: directory name)')
    index_files_parser.add_argument('--merge-with', metavar='URL',
                                    help='Merge into existing site index')
    index_files_parser.add_argument('--no-headers', action='store_true',
                                    help='Do not treat first Excel row as headers')
    index_files_parser.add_argument('--max-rows', type=int, default=None,
                                    help='Maximum rows to extract per sheet (default: no limit)')
    index_files_parser.add_argument('--quiet', '-q', action='store_true',
                                    help='Suppress progress output')
    index_files_parser.add_argument('--force', '-f', action='store_true',
                                    help='Force re-index all files (ignore cache)')
    index_files_parser.add_argument('--clean', action='store_true',
                                    help='Remove documents for deleted source files')
    index_files_parser.set_defaults(func=cmd_index_files)


def _add_search_parser(subparsers):
    """Add the search command parser."""
    search_parser = subparsers.add_parser('search', help='Search the index')
    search_parser.add_argument('site_dir', help='Site data directory or original URL')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--limit', '-l', type=int, default=10,
                              help='Number of results (default: 10)')
    search_parser.add_argument('--scores', '-s', action='store_true',
                              help='Show BM25 scores')
    search_parser.add_argument('--json', '-j', action='store_true',
                              help='Output as JSON')
    search_parser.add_argument('--quiet', '-q', action='store_true',
                              help='Suppress loading messages')
    search_parser.add_argument('--no-color', action='store_true',
                              help='Disable colored output')
    search_parser.add_argument('--synonyms', action='store_true', default=False,
                              dest='synonyms',
                              help='Enable synonym expansion (default: off)')
    search_parser.add_argument('--no-synonyms', action='store_false',
                              dest='synonyms',
                              help='Disable synonym expansion')
    search_parser.add_argument('--synonyms-file', metavar='FILE',
                              help='Load custom synonyms from JSON file')
    search_parser.add_argument('--no-facets', action='store_true',
                              help='Disable faceted search')
    search_parser.add_argument('--show-facets', action='store_true',
                              help='Show facet counts in output')
    search_parser.add_argument('--filter-category', metavar='CATEGORY',
                              help='Filter by URL path category (e.g., library, tutorial, api)')
    search_parser.add_argument('--filter-section', metavar='SECTION',
                              help='Filter by section name')
    search_parser.add_argument('--no-symspell', action='store_true',
                              help='Disable SymSpell suggestions (use basic spellcheck)')
    search_parser.add_argument('--no-ngram', action='store_true',
                              help='Disable n-gram prefix/substring search')
    search_parser.add_argument('--separate-paths', action='store_true',
                              help='Use if site was crawled with --separate-paths')
    search_parser.set_defaults(func=cmd_search)


def _add_search_all_parser(subparsers):
    """Add the search-all command parser."""
    search_all_parser = subparsers.add_parser(
        'search-all', 
        help='Search across all crawled sites'
    )
    search_all_parser.add_argument('query', help='Search query')
    search_all_parser.add_argument('--limit', '-l', type=int, default=10,
                                   help='Total number of results (default: 10)')
    search_all_parser.add_argument('--sites', nargs='+', metavar='SITE',
                                   help='Filter to specific sites (by URL substring or hash prefix)')
    search_all_parser.add_argument('--scores', '-s', action='store_true',
                                   help='Show BM25 scores')
    search_all_parser.add_argument('--json', '-j', action='store_true',
                                   help='Output as JSON')
    search_all_parser.add_argument('--quiet', '-q', action='store_true',
                                   help='Suppress loading messages')
    search_all_parser.add_argument('--no-color', action='store_true',
                                   help='Disable colored output')
    search_all_parser.set_defaults(func=cmd_search_all)


def _add_autocomplete_parser(subparsers):
    """Add the autocomplete command parser."""
    auto_parser = subparsers.add_parser('autocomplete', help='Get search suggestions (multi-term, fuzzy matching)')
    auto_parser.add_argument('site_dir', help='Site data directory or original URL')
    auto_parser.add_argument('prefix', help='Prefix to get suggestions for')
    auto_parser.add_argument('--limit', '-l', type=int, default=10,
                            help='Maximum suggestions (default: 10)')
    auto_parser.add_argument('--json', '-j', action='store_true',
                            help='Output as JSON')
    auto_parser.set_defaults(func=cmd_autocomplete)


def _add_interactive_parser(subparsers):
    """Add the interactive command parser."""
    interactive_parser = subparsers.add_parser('interactive', help='Interactive search mode')
    interactive_parser.add_argument('site_dir', help='Site data directory or original URL')
    interactive_parser.add_argument('--limit', '--per-page', '-l', type=int, default=10, dest='limit',
                                   help='Results per page (default: 10)')
    interactive_parser.add_argument('--max-results', '-m', type=int, default=100, dest='max_results',
                                   help='Max results to fetch per query (default: 100)')
    interactive_parser.add_argument('--scores', '-s', action='store_true',
                                   help='Show BM25 scores')
    interactive_parser.add_argument('--no-symspell', action='store_true',
                                   help='Disable SymSpell suggestions (use basic spellcheck)')
    interactive_parser.add_argument('--no-ngram', action='store_true',
                                   help='Disable n-gram prefix/substring search')
    interactive_parser.add_argument('--synonyms', action='store_true', default=False,
                                   dest='synonyms',
                                   help='Enable synonym expansion (default: off)')
    interactive_parser.add_argument('--no-synonyms', action='store_false',
                                   dest='synonyms',
                                   help='Disable synonym expansion')
    interactive_parser.add_argument('--synonyms-file', metavar='FILE',
                                   help='Load custom synonyms from JSON file')
    interactive_parser.add_argument('--separate-paths', action='store_true',
                                   help='Use if site was crawled with --separate-paths')
    interactive_parser.set_defaults(func=cmd_interactive)


def _add_stats_parser(subparsers):
    """Add the stats command parser."""
    stats_parser = subparsers.add_parser('stats', help='Show site statistics')
    stats_parser.add_argument('site_dir', help='Site data directory or original URL')
    stats_parser.add_argument('--show-errors', '-e', action='store_true',
                             help='Show detailed list of crawl errors')
    stats_parser.add_argument('--separate-paths', action='store_true',
                             help='Use if site was crawled with --separate-paths')
    stats_parser.set_defaults(func=cmd_stats)


def _add_list_parser(subparsers):
    """Add the list command parser."""
    list_parser = subparsers.add_parser('list', help='List crawled sites')
    list_parser.add_argument('--refresh', action='store_true',
                             help='Rebuild doc type counts from page files (slow, updates metadata cache)')
    list_parser.set_defaults(func=cmd_list)


def _add_delete_parser(subparsers):
    """Add the delete command parser."""
    delete_parser = subparsers.add_parser('delete', help='Delete crawled site(s)')
    delete_parser.add_argument('site', nargs='*', help='Site URL(s) or hash ID(s) to delete')
    delete_parser.add_argument('--all', '-a', action='store_true',
                              help='Delete all crawled sites')
    delete_parser.add_argument('--dry-run', '-n', action='store_true',
                              help='Show what would be deleted without actually deleting')
    delete_parser.set_defaults(func=cmd_delete)


def _add_serve_parser(subparsers):
    """Add the serve command parser."""
    serve_parser = subparsers.add_parser('serve', help='Start web UI server')
    serve_parser.add_argument('site_dir', nargs='?', default=None,
                             help='Site data directory or original URL (not needed with --all)')
    serve_parser.add_argument('--all', '-a', action='store_true',
                             help='Multi-site mode: search across all indexed sites')
    serve_parser.add_argument('--sites', nargs='+', metavar='SITE',
                             help='Filter to specific sites in multi-site mode (by URL or hash prefix)')
    serve_parser.add_argument('--port', '-p', type=int, default=8282,
                             help='Port to listen on (default: 8282)')
    serve_parser.add_argument('--host', default='127.0.0.1',
                             help='Host to bind to (default: 127.0.0.1)')
    serve_parser.add_argument('--open', '-o', action='store_true',
                             help='Open browser automatically')
    serve_parser.add_argument('--log-requests', action='store_true',
                             help='Log HTTP requests to stdout')
    serve_parser.add_argument('--per-page', type=int, default=10,
                             help='Results per page (default: 10)')
    serve_parser.add_argument('--max-results', type=int, default=100,
                             help='Maximum total results for pagination (default: 100)')
    serve_parser.add_argument('--separate-paths', action='store_true',
                             help='Use if site was crawled with --separate-paths')
    serve_parser.add_argument('--enable-synonyms', action='store_true', default=False,
                             dest='enable_synonyms',
                             help='Enable synonym expansion (default: off)')
    serve_parser.add_argument('--disable-synonyms', action='store_false',
                             dest='enable_synonyms',
                             help='Disable synonym expansion')
    serve_parser.add_argument('--synonyms-file', metavar='FILE',
                             help='Load custom synonyms from JSON file')
    serve_parser.add_argument('--cache-size', type=int, default=128,
                             help='Number of search queries to cache (default: 128, 0 to disable)')
    serve_parser.add_argument('--cache-ttl', type=float, default=0,
                             help='Cache TTL in seconds (default: 0 = never expire, only evict when full)')
    serve_parser.add_argument('--cache-file', type=str, default=None,
                             help='Path to cache file (default: <site_dir>/.cache.db)')
    serve_parser.add_argument('--no-javascript', action='store_true',
                             help='Serve pure HTML/CSS UI without JavaScript')
    serve_parser.add_argument('--suggestions', action='store_true', default=False,
                             help='Enable autocomplete suggestions (default: off)')
    serve_parser.add_argument('--no-symspell', action='store_true',
                             help='Disable SymSpell suggestions (use basic spellcheck)')
    serve_parser.add_argument('--no-ngram', action='store_true',
                             help='Disable n-gram prefix/substring search')
    serve_parser.set_defaults(func=cmd_serve)
