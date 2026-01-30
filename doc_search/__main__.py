#!/usr/bin/env python3
"""
doc_search - CLI for crawling and searching documentation sites.

Usage:
    python -m doc_search crawl <url> [options]
    python -m doc_search index <site_dir>
    python -m doc_search search <site_dir> <query>
    python -m doc_search interactive <site_dir>
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from . import __version__
from .crawler import Crawler
from .indexer import BM25Index
from .searcher import SearchEngine, format_results
from .utils import site_hash, format_size, format_duration


# Default data directory
DEFAULT_DATA_DIR = Path.home() / '.doc_search' / 'sites'


def get_site_dir(url_or_path: str) -> Path:
    """Get site data directory from URL or existing path."""
    path = Path(url_or_path)
    
    # If it's an existing directory, use it
    if path.is_dir():
        return path
    
    # Otherwise, treat as URL and generate directory
    return DEFAULT_DATA_DIR / site_hash(url_or_path)


def get_auth(args) -> Optional[Tuple[str, str]]:
    """Get authentication credentials from args or prompt."""
    if args.user:
        if args.password:
            return (args.user, args.password)
        else:
            password = getpass.getpass(f"Password for {args.user}: ")
            return (args.user, password)
    return None


def cmd_crawl(args):
    """Crawl a documentation site."""
    site_dir = get_site_dir(args.url)
    site_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Crawling: {args.url}")
    print(f"Data directory: {site_dir}")
    print()
    
    # Get authentication
    auth = get_auth(args)
    
    # Create crawler
    crawler = Crawler(
        base_url=args.url,
        data_dir=site_dir,
        delay=args.delay,
        timeout=args.timeout,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        auth=auth,
        same_path=not args.no_same_path,
        verbose=not args.quiet
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
    site_dir = get_site_dir(args.site_dir)
    pages_dir = site_dir / 'pages'
    
    if not pages_dir.exists():
        print(f"Error: No crawled pages found in {site_dir}")
        print("Run 'doc_search crawl <url>' first.")
        return 1
    
    print(f"Building index from: {pages_dir}")
    
    # Build index
    index = BM25Index(k1=args.k1, b=args.b)
    num_docs = index.build_from_pages(pages_dir, verbose=not args.quiet)
    
    if num_docs == 0:
        print("Error: No documents to index.")
        return 1
    
    # Save index
    index_path = index.save(site_dir / 'index', compress=not args.no_compress)
    
    print(f"\nIndex saved to: {index_path}")
    print(f"Index size: {format_size(index_path.stat().st_size)}")
    
    return 0


def cmd_search(args):
    """Search the index."""
    site_dir = get_site_dir(args.site_dir)
    
    # Find index file
    index_path = None
    for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
        if candidate.exists():
            index_path = candidate
            break
    
    if not index_path:
        print(f"Error: No index found in {site_dir}")
        print("Run 'doc_search index <site_dir>' first.")
        return 1
    
    # Load index
    if not args.quiet:
        print(f"Loading index from: {index_path}")
    
    engine = SearchEngine.load(index_path)
    
    # Search
    results = engine.search(args.query, top_k=args.limit)
    
    # Output results
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_results(results, show_scores=args.scores))
    
    return 0


def cmd_interactive(args):
    """Interactive search mode."""
    site_dir = get_site_dir(args.site_dir)
    
    # Find index file
    index_path = None
    for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
        if candidate.exists():
            index_path = candidate
            break
    
    if not index_path:
        print(f"Error: No index found in {site_dir}")
        print("Run 'doc_search index <site_dir>' first.")
        return 1
    
    # Load index
    print(f"Loading index from: {index_path}")
    engine = SearchEngine.load(index_path)
    
    stats = engine.get_stats()
    print(f"Loaded {stats['total_documents']} documents, {stats['unique_terms']} unique terms")
    print()
    print("Enter search queries (empty line to quit):")
    print()
    
    while True:
        try:
            query = input("search> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        
        if not query:
            break
        
        results = engine.search(query, top_k=args.limit)
        print()
        print(format_results(results, show_scores=args.scores))
    
    return 0


def cmd_stats(args):
    """Show statistics for a crawled site."""
    site_dir = get_site_dir(args.site_dir)
    
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
  
  # Crawl entire domain (ignore path restriction)
  python -m doc_search crawl https://docs.example.com --no-same-path
  
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
    crawl_parser.add_argument('--delay', '-d', type=float, default=1.0,
                             help='Delay between requests in seconds (default: 1.0)')
    crawl_parser.add_argument('--timeout', '-t', type=float, default=30.0,
                             help='Request timeout in seconds (default: 30)')
    crawl_parser.add_argument('--max-pages', '-m', type=int,
                             help='Maximum number of pages to crawl')
    crawl_parser.add_argument('--max-depth', type=int,
                             help='Maximum link depth from starting URL')
    crawl_parser.add_argument('--no-same-path', action='store_true',
                             help='Allow crawling outside the starting path (default: stay under starting path)')
    crawl_parser.add_argument('--fresh', '-f', action='store_true',
                             help='Start fresh crawl (ignore saved state)')
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
    search_parser.set_defaults(func=cmd_search)
    
    # Interactive command
    interactive_parser = subparsers.add_parser('interactive', help='Interactive search mode')
    interactive_parser.add_argument('site_dir', help='Site data directory or original URL')
    interactive_parser.add_argument('--limit', '-l', type=int, default=10,
                                   help='Number of results per query (default: 10)')
    interactive_parser.add_argument('--scores', '-s', action='store_true',
                                   help='Show BM25 scores')
    interactive_parser.set_defaults(func=cmd_interactive)
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show site statistics')
    stats_parser.add_argument('site_dir', help='Site data directory or original URL')
    stats_parser.set_defaults(func=cmd_stats)
    
    # List command
    list_parser = subparsers.add_parser('list', help='List crawled sites')
    list_parser.set_defaults(func=cmd_list)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
