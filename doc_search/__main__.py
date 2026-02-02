#!/usr/bin/env python3
"""
doc_search - CLI for crawling and searching documentation sites.

Usage:
    python -m doc_search crawl <url> [options]
    python -m doc_search index <site_dir>
    python -m doc_search search <site_dir> <query>
    python -m doc_search interactive <site_dir>
    python -m doc_search serve <site_dir> [--port PORT]
"""

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

from . import __version__
from .crawler import Crawler
from .indexer import BM25Index
from .searcher import SearchEngine, EnhancedSearchEngine, format_results, parse_query
from .utils import (
    site_hash, format_size, format_duration,
    Colors, colorize, style_success, style_error, style_info, style_title, style_url
)


# Default data directory
DEFAULT_DATA_DIR = Path.home() / '.doc_search' / 'sites'


def get_site_dir(url_or_path: str, include_path: bool = False) -> Path:
    """Get site data directory from URL or existing path.
    
    Args:
        url_or_path: URL or existing directory path
        include_path: If True, include URL path in hash (separate storage per path)
    """
    path = Path(url_or_path)
    
    # If it's an existing directory, use it
    if path.is_dir():
        return path
    
    # Otherwise, treat as URL and generate directory
    return DEFAULT_DATA_DIR / site_hash(url_or_path, include_path=include_path)


def get_auth(args) -> Tuple[Optional[Tuple[str, str]], Optional[str]]:
    """Get authentication credentials from args or prompt.
    
    Returns:
        (auth_tuple, auth_token) where auth_tuple is (username, password)
        and auth_token is pre-encoded base64 token. One or both may be None.
    """
    auth_token = getattr(args, 'token', None)
    
    if args.user:
        if args.password:
            return ((args.user, args.password), auth_token)
        else:
            password = getpass.getpass(f"Password for {args.user}: ")
            return ((args.user, password), auth_token)
    
    return (None, auth_token)


def cmd_crawl(args):
    """Crawl a documentation site."""
    separate_paths = getattr(args, 'separate_paths', False)
    site_dir = get_site_dir(args.url, include_path=separate_paths)
    site_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Crawling: {args.url}")
    print(f"Data directory: {site_dir}")
    if separate_paths:
        print(f"Storage mode: separate paths")
    print()
    
    # Get authentication
    auth, auth_token = get_auth(args)
    
    # Create crawler
    crawler = Crawler(
        base_url=args.url,
        data_dir=site_dir,
        delay=args.delay,
        timeout=args.timeout,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        auth=auth,
        auth_token=auth_token,
        same_path=getattr(args, 'same_path', False),
        verbose=not args.quiet,
        workers=args.workers,
        extract_docs=args.extract_docs,
        incremental=getattr(args, 'incremental', False)
    )
    
    # Start crawling
    stats = crawler.crawl(resume=not args.fresh)
    
    # Save site metadata
    metadata = {
        'url': args.url,
        'stats': stats
    }
    with open(site_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nSite data saved to: {site_dir}")
    return 0


def cmd_index(args):
    """Build search index from crawled pages."""
    separate_paths = getattr(args, 'separate_paths', False)
    site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    pages_dir = site_dir / 'pages'
    
    if not pages_dir.exists():
        print(f"Error: No crawled pages found in {site_dir}")
        print("Run 'doc_search crawl <url>' first.")
        return 1
    
    print(f"Building index from: {pages_dir}")
    
    # Build index
    stem = not getattr(args, 'no_stemming', False)
    index = BM25Index(k1=args.k1, b=args.b, stem=stem)
    num_docs = index.build_from_pages(pages_dir, verbose=not args.quiet)
    
    if not args.quiet:
        print(f"Stemming: {'enabled' if stem else 'disabled'}")
    
    if num_docs == 0:
        print("Error: No documents to index.")
        return 1
    
    # Save index
    index_path = index.save(site_dir / 'index', compress=not args.no_compress)
    
    print(f"\nIndex saved to: {index_path}")
    print(f"Index size: {format_size(index_path.stat().st_size)}")
    
    return 0


def cmd_search(args):
    """Search the index with enhanced features."""
    separate_paths = getattr(args, 'separate_paths', False)
    site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    
    # Find index file
    index_path = None
    for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
        if candidate.exists():
            index_path = candidate
            break
    
    if not index_path:
        print(style_error(f"Error: No index found in {site_dir}"))
        print("Run 'doc_search index <site_dir>' first.")
        return 1
    
    # Load index (use enhanced engine for new features)
    if not args.quiet:
        print(style_info(f"Loading index from: {index_path}"))
    
    # Check for enhanced features flags
    use_enhanced = not getattr(args, 'basic', False)
    
    # Load custom synonyms if file provided
    custom_synonyms = None
    synonyms_file = getattr(args, 'synonyms_file', None)
    if synonyms_file:
        try:
            with open(synonyms_file, 'r') as f:
                data = json.load(f)
            # Expect {"groups": [["term1", "term2"], ["term3", "term4"]]}
            custom_synonyms = [set(group) for group in data.get('groups', [])]
            if not args.quiet:
                print(style_info(f"Loaded {len(custom_synonyms)} synonym groups from {synonyms_file}"))
        except (IOError, json.JSONDecodeError) as e:
            print(style_error(f"Error loading synonyms file: {e}"))
            return 1
    
    if use_enhanced:
        engine = EnhancedSearchEngine.load(
            index_path,
            enable_spellcheck=True,
            enable_autocomplete=True,
            enable_facets=not getattr(args, 'no_facets', False),
            enable_synonyms=getattr(args, 'synonyms', False) or custom_synonyms is not None,
            synonym_groups=custom_synonyms
        )
    else:
        engine = SearchEngine.load(index_path)
    
    # Time the search
    start_time = time.perf_counter()
    
    if use_enhanced:
        # Get facet filter if specified
        facet_filters = {}
        if hasattr(args, 'filter_category') and args.filter_category:
            facet_filters['category'] = args.filter_category
        if hasattr(args, 'filter_section') and args.filter_section:
            facet_filters['section'] = args.filter_section
        
        response = engine.search(
            args.query, 
            top_k=args.limit,
            facet_filters=facet_filters if facet_filters else None,
            expand_synonyms=getattr(args, 'synonyms', False) or custom_synonyms is not None
        )
        results = response['results']
        suggestion = response.get('suggestion')
        expanded_query = response.get('expanded_query')
        facets = response.get('facets', {})
    else:
        results = engine.search(args.query, top_k=args.limit)
        suggestion = None
        expanded_query = None
        facets = {}
    
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    # Get query terms for highlighting
    terms, phrases = parse_query(args.query)
    query_terms = set(terms)
    for phrase in phrases:
        query_terms.update(phrase)
    
    # Output results
    if args.json:
        output = {
            'query': args.query,
            'elapsed_ms': round(elapsed_ms, 2),
            'count': len(results),
            'results': results
        }
        if suggestion:
            output['suggestion'] = suggestion
        if expanded_query:
            output['expanded_query'] = expanded_query
        if facets:
            output['facets'] = facets
        print(json.dumps(output, indent=2))
    else:
        print()
        
        # Show "Did you mean..." suggestion
        if suggestion and not args.quiet:
            print(style_info(f'💡 Did you mean: "{suggestion}"?'))
            print()
        
        print(format_results(
            results, 
            show_scores=args.scores,
            query_terms=query_terms,
            elapsed_ms=elapsed_ms,
            colorize_output=not args.no_color
        ))
        
        # Show facet counts if available
        if facets and not args.quiet and getattr(args, 'show_facets', False):
            print(style_info("📊 Facets:"))
            for ftype, values in facets.items():
                print(f"  {ftype}:")
                for value, count in sorted(values.items(), key=lambda x: -x[1])[:5]:
                    print(f"    {value}: {count}")
            print()
    
    return 0


def cmd_autocomplete(args):
    """Get autocomplete suggestions for a prefix."""
    separate_paths = getattr(args, 'separate_paths', False)
    site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    
    # Find index file
    index_path = None
    for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
        if candidate.exists():
            index_path = candidate
            break
    
    if not index_path:
        print(style_error(f"Error: No index found in {site_dir}"))
        print("Run 'doc_search index <site_dir>' first.")
        return 1
    
    engine = EnhancedSearchEngine.load(index_path)
    suggestions = engine.get_autocomplete_suggestions(args.prefix, max_suggestions=args.limit)
    
    if args.json:
        print(json.dumps({'prefix': args.prefix, 'suggestions': suggestions}))
    else:
        if suggestions:
            for s in suggestions:
                print(s)
        else:
            print(style_info("No suggestions found."))
    
    return 0


def cmd_interactive(args):
    """Interactive search mode with beautiful colored output and enhanced features."""
    separate_paths = getattr(args, 'separate_paths', False)
    site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    
    # Find index file
    index_path = None
    for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
        if candidate.exists():
            index_path = candidate
            break
    
    if not index_path:
        print(style_error(f"Error: No index found in {site_dir}"))
        print("Run 'doc_search index <site_dir>' first.")
        return 1
    
    # Load enhanced engine
    print(style_info(f"Loading index from: {index_path}"))
    engine = EnhancedSearchEngine.load(index_path)
    
    stats = engine.get_stats()
    
    # Beautiful header
    print()
    print(style_title("╔═══════════════════════════════════════════════════════════════╗"))
    print(style_title("║") + "              " + style_success("doc-search") + " — Interactive Mode              " + style_title("║"))
    print(style_title("╚═══════════════════════════════════════════════════════════════╝"))
    print()
    print(f"  📚 {style_info(str(stats['total_documents']))} documents indexed")
    print(f"  🔤 {style_info(str(stats['unique_terms']))} unique terms")
    print(f"  📏 {style_info(str(stats['avg_document_length']))} avg terms per document")
    
    # Show enabled features
    features = stats.get('features', {})
    enabled = [k for k, v in features.items() if v]
    if enabled:
        print(f"  ✨ Features: {', '.join(enabled)}")
    
    print()
    print(style_info("  Type a query and press Enter. Empty line or Ctrl+C to exit."))
    print(style_info("  Tip: Use \"quotes\" for phrase search"))
    print()
    
    prompt = f"{Colors.BRIGHT_CYAN}search>{Colors.RESET} "
    
    while True:
        try:
            query = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(style_info("\nGoodbye! 👋"))
            break
        
        if not query:
            print(style_info("\nGoodbye! 👋"))
            break
        
        # Time the search
        start_time = time.perf_counter()
        response = engine.search(query, top_k=args.limit)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        results = response['results']
        suggestion = response.get('suggestion')
        
        # Get query terms for highlighting
        terms, phrases = parse_query(query)
        query_terms = set(terms)
        for phrase in phrases:
            query_terms.update(phrase)
        
        print()
        
        # Show "Did you mean..." suggestion
        if suggestion:
            print(style_info(f'💡 Did you mean: "{suggestion}"?'))
            print()
        
        print(format_results(
            results, 
            show_scores=args.scores,
            query_terms=query_terms,
            elapsed_ms=elapsed_ms,
            colorize_output=True
        ))
    
    return 0


def cmd_stats(args):
    """Show statistics for a crawled site."""
    separate_paths = getattr(args, 'separate_paths', False)
    site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    
    if not site_dir.exists():
        print(f"Error: Site directory not found: {site_dir}")
        return 1
    
    # Load metadata
    metadata_file = site_dir / 'metadata.json'
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)
        print(f"Site: {metadata.get('url', 'Unknown')}")
        print()
        
        stats = metadata.get('stats', {})
        print("Crawl Statistics:")
        print(f"  Pages crawled: {stats.get('pages_crawled', 0)}")
        print(f"  Pages skipped: {stats.get('pages_skipped', 0)}")
        print(f"  Pages failed: {stats.get('pages_failed', 0)}")
        print(f"  Data downloaded: {format_size(stats.get('bytes_downloaded', 0))}")
        if stats.get('elapsed_seconds'):
            print(f"  Time elapsed: {format_duration(stats['elapsed_seconds'])}")
        print()
    
    # Count page files
    pages_dir = site_dir / 'pages'
    if pages_dir.exists():
        page_count = len(list(pages_dir.glob('*.json')))
        total_size = sum(f.stat().st_size for f in pages_dir.glob('*.json'))
        print(f"Stored Pages: {page_count} ({format_size(total_size)})")
    
    # Index stats
    index_path = None
    for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
        if candidate.exists():
            index_path = candidate
            break
    
    if index_path:
        engine = SearchEngine.load(index_path)
        idx_stats = engine.get_stats()
        print()
        print("Index Statistics:")
        print(f"  Documents: {idx_stats['total_documents']}")
        print(f"  Unique terms: {idx_stats['unique_terms']}")
        print(f"  Avg document length: {idx_stats['avg_document_length']} terms")
        print(f"  BM25 k1={idx_stats['k1']}, b={idx_stats['b']}")
        print(f"  Index size: {format_size(index_path.stat().st_size)}")
    
    return 0


def cmd_list(args):
    """List all crawled sites."""
    if not DEFAULT_DATA_DIR.exists():
        print("No sites crawled yet.")
        return 0
    
    sites = list(DEFAULT_DATA_DIR.iterdir())
    if not sites:
        print("No sites crawled yet.")
        return 0
    
    print(f"Crawled sites ({len(sites)}):")
    print()
    
    for site_dir in sorted(sites):
        if not site_dir.is_dir():
            continue
        
        metadata_file = site_dir / 'metadata.json'
        if metadata_file.exists():
            with open(metadata_file) as f:
                metadata = json.load(f)
            url = metadata.get('url', 'Unknown')
            pages = metadata.get('stats', {}).get('pages_crawled', 0)
            print(f"  {site_dir.name}: {url} ({pages} pages)")
        else:
            print(f"  {site_dir.name}: (no metadata)")
    
    print()
    print(f"Data directory: {DEFAULT_DATA_DIR}")
    
    return 0


def cmd_serve(args):
    """Start the web UI server for searching."""
    import webbrowser
    from .server import run_server
    
    separate_paths = getattr(args, 'separate_paths', False)
    site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    
    # Find index file
    index_path = None
    for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
        if candidate.exists():
            index_path = candidate
            break
    
    if not index_path:
        print(style_error(f"Error: No index found in {site_dir}"))
        print("Run 'doc_search index <site_dir>' first.")
        return 1
    
    # Load index
    print(style_info(f"Loading index from: {index_path}"))
    engine = SearchEngine.load(index_path)
    
    stats = engine.get_stats()
    
    # Start server
    log_requests = getattr(args, 'log_requests', False)
    server = run_server(engine, host=args.host, port=args.port, version=__version__, log_requests=log_requests)
    
    url = f"http://{args.host}:{args.port}"
    
    # Beautiful startup message
    print()
    print(style_title("╔═══════════════════════════════════════════════════════════════╗"))
    print(style_title("║") + "              " + style_success("doc-search") + " — Web UI Server                 " + style_title("║"))
    print(style_title("╚═══════════════════════════════════════════════════════════════╝"))
    print()
    print(f"  🌐 Server running at: {style_url(url)}")
    print(f"  📚 {style_info(str(stats['total_documents']))} documents indexed")
    print(f"  🔤 {style_info(str(stats['unique_terms']))} unique terms")
    print()
    print(style_info("  Press Ctrl+C to stop the server"))
    print()
    
    # Open browser if requested
    if args.open:
        webbrowser.open(url)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print(style_info("\nServer stopped. Goodbye! 👋"))
    
    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='doc_search',
        description='Search through large documentation websites.',
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
    
    # Crawl command
    crawl_parser = subparsers.add_parser('crawl', help='Crawl a documentation site')
    crawl_parser.add_argument('url', help='Base URL to crawl')
    crawl_parser.add_argument('--user', '-u', help='Username for HTTP Basic Auth')
    crawl_parser.add_argument('--password', '-p', help='Password (will prompt if not provided)')
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
    crawl_parser.add_argument('--fresh', '-f', action='store_true',
                             help='Start fresh crawl (ignore saved state)')
    crawl_parser.add_argument('--incremental', '-i', action='store_true',
                             help='Only re-download pages that have changed since last crawl')
    crawl_parser.add_argument('--workers', '-w', type=int, default=1,
                             help='Number of parallel workers (default: 1 for politeness)')
    crawl_parser.add_argument('--extract-docs', action='store_true',
                             help='Extract text from PDFs and Office documents')
    crawl_parser.add_argument('--separate-paths', action='store_true',
                             help='Store different URL paths separately (e.g., /3.11/ and /3.12/ get their own folders)')
    crawl_parser.add_argument('--quiet', '-q', action='store_true',
                             help='Suppress progress output')
    crawl_parser.set_defaults(func=cmd_crawl)
    
    # Index command
    index_parser = subparsers.add_parser('index', help='Build search index')
    index_parser.add_argument('site_dir', help='Site data directory or original URL')
    index_parser.add_argument('--k1', type=float, default=1.5,
                             help='BM25 k1 parameter (default: 1.5)')
    index_parser.add_argument('--b', type=float, default=0.75,
                             help='BM25 b parameter (default: 0.75)')
    index_parser.add_argument('--no-compress', action='store_true',
                             help='Don\'t compress the index file')
    index_parser.add_argument('--no-stemming', action='store_true',
                             help='Disable Porter stemming')
    index_parser.add_argument('--separate-paths', action='store_true',
                             help='Use if site was crawled with --separate-paths')
    index_parser.add_argument('--quiet', '-q', action='store_true',
                             help='Suppress progress output')
    index_parser.set_defaults(func=cmd_index)
    
    # Search command
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
    # Enhanced features
    search_parser.add_argument('--basic', action='store_true',
                              help='Use basic search (disable enhanced features)')
    search_parser.add_argument('--synonyms', action='store_true',
                              help='Enable synonym expansion (built-in programming terms)')
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
    search_parser.add_argument('--separate-paths', action='store_true',
                              help='Use if site was crawled with --separate-paths')
    search_parser.set_defaults(func=cmd_search)
    
    # Autocomplete command
    auto_parser = subparsers.add_parser('autocomplete', help='Get autocomplete suggestions')
    auto_parser.add_argument('site_dir', help='Site data directory or original URL')
    auto_parser.add_argument('prefix', help='Prefix to get suggestions for')
    auto_parser.add_argument('--limit', '-l', type=int, default=10,
                            help='Maximum suggestions (default: 10)')
    auto_parser.add_argument('--json', '-j', action='store_true',
                            help='Output as JSON')
    auto_parser.set_defaults(func=cmd_autocomplete)
    
    # Interactive command
    interactive_parser = subparsers.add_parser('interactive', help='Interactive search mode')
    interactive_parser.add_argument('site_dir', help='Site data directory or original URL')
    interactive_parser.add_argument('--limit', '-l', type=int, default=10,
                                   help='Number of results per query (default: 10)')
    interactive_parser.add_argument('--scores', '-s', action='store_true',
                                   help='Show BM25 scores')
    interactive_parser.add_argument('--separate-paths', action='store_true',
                                   help='Use if site was crawled with --separate-paths')
    interactive_parser.set_defaults(func=cmd_interactive)
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show site statistics')
    stats_parser.add_argument('site_dir', help='Site data directory or original URL')
    stats_parser.add_argument('--separate-paths', action='store_true',
                             help='Use if site was crawled with --separate-paths')
    stats_parser.set_defaults(func=cmd_stats)
    
    # List command
    list_parser = subparsers.add_parser('list', help='List crawled sites')
    list_parser.set_defaults(func=cmd_list)
    
    # Serve command (web UI)
    serve_parser = subparsers.add_parser('serve', help='Start web UI server')
    serve_parser.add_argument('site_dir', help='Site data directory or original URL')
    serve_parser.add_argument('--port', '-p', type=int, default=8080,
                             help='Port to listen on (default: 8080)')
    serve_parser.add_argument('--host', default='127.0.0.1',
                             help='Host to bind to (default: 127.0.0.1)')
    serve_parser.add_argument('--open', '-o', action='store_true',
                             help='Open browser automatically')
    serve_parser.add_argument('--log-requests', action='store_true',
                             help='Log HTTP requests to stdout')
    serve_parser.add_argument('--separate-paths', action='store_true',
                             help='Use if site was crawled with --separate-paths')
    serve_parser.set_defaults(func=cmd_serve)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
