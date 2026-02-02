"""
Command implementations for doc-search CLI.

This module contains all the cmd_* functions that implement
the various CLI commands (crawl, index, search, etc.).
"""

import getpass
import json
import time
from pathlib import Path
from typing import Optional, Tuple

from ..crawler import Crawler
from ..indexer import BM25Index
from ..searcher import SearchEngine, EnhancedSearchEngine, format_results, parse_query
from ..utils import (
    site_hash, format_size, format_duration,
    Colors, style_success, style_error, style_info, style_title, style_url
)
from .. import __version__


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
    from ..server import run_server
    
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
    per_page = getattr(args, 'per_page', 10)
    max_results = getattr(args, 'max_results', 100)
    server = run_server(engine, host=args.host, port=args.port, version=__version__, 
                       log_requests=log_requests, per_page=per_page, max_results=max_results)
    
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
