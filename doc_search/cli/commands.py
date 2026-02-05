"""
Command implementations for doc-search CLI.

This module contains all the cmd_* functions that implement
the various CLI commands (crawl, index, search, etc.).

API Usage:
    All CLI commands use the unified search API:
    - cmd_search: Uses EnhancedSearchEngine.search_enhanced() or SearchEngine.search()
    - cmd_serve: Uses SearchEngine.search() via the web server
    - cmd_autocomplete: Uses EnhancedSearchEngine.get_autocomplete_suggestions()
    - cmd_interactive: Uses EnhancedSearchEngine.search_enhanced()
    - cmd_stats: Uses SearchEngine.get_stats()
    
    Note: The deprecated search_simple() method is NOT used by the CLI.
"""

import getpass
import json
import os
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


# Emoji fallbacks for systems without emoji support
# Set DOC_SEARCH_NO_EMOJI=1 to use ASCII alternatives
_NO_EMOJI = os.environ.get('DOC_SEARCH_NO_EMOJI', '').lower() in ('1', 'true', 'yes')

_EMOJI_MAP = {
    'bulb': ('💡', '*'),
    'chart': ('📊', '#'),
    'terms': ('🔤', 'T:'),
    'globe': ('🌐', '@'),
    'folder': ('📁', '>'),
    'check': ('✓', '+'),
    'cross': ('✗', 'x'),
    'docs': ('📄', '-'),
    'books': ('📚', 'D:'),
    'ruler': ('📏', 'A:'),
    'sparkles': ('✨', '*'),
}

def _e(name: str) -> str:
    """Get emoji or ASCII fallback based on DOC_SEARCH_NO_EMOJI env var."""
    emoji, fallback = _EMOJI_MAP.get(name, ('', ''))
    return fallback if _NO_EMOJI else emoji


# Default data directory
DEFAULT_DATA_DIR = Path.home() / '.doc_search' / 'sites'


def get_site_dir(url_or_path: str, include_path: bool = False) -> Path:
    """Get site data directory from URL or existing path.
    
    Args:
        url_or_path: URL or existing directory path
        include_path: If True, include URL path in hash (separate storage per path)
    
    Returns:
        Path to the site data directory
    
    Raises:
        ValueError: If input is neither a valid URL nor an existing directory
    """
    # Check if it's a URL (http:// or https://)
    if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
        return DEFAULT_DATA_DIR / site_hash(url_or_path, include_path=include_path)
    
    # Not a URL - must be an existing directory path
    path = Path(url_or_path)
    
    # Check if path exists
    if not path.exists():
        raise ValueError(
            f"Directory not found: {url_or_path}\n"
            f"If this is a URL, it must start with http:// or https://\n"
            f"If this is a path, the directory must exist."
        )
    
    # Check if it's actually a directory (not a file)
    if not path.is_dir():
        raise ValueError(
            f"Not a directory: {url_or_path}\n"
            f"Expected a directory path, but found a file."
        )
    
    return path


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
    try:
        site_dir = get_site_dir(args.url, include_path=separate_paths)
    except ValueError as e:
        print(style_error(f"Error: {e}"))
        return 1
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
        ignore_robots=getattr(args, 'ignore_robots', False),
        verbose=not args.quiet,
        workers=args.workers,
        extract_docs=args.extract_docs,
        incremental=getattr(args, 'incremental', False),
        save_html=not getattr(args, 'no_save_html', False),
        parser=getattr(args, 'parser', 'dom')
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
    try:
        site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    except ValueError as e:
        print(style_error(f"Error: {e}"))
        return 1
    pages_dir = site_dir / 'pages'
    
    if not pages_dir.exists():
        print(f"Error: No crawled pages found in {site_dir}")
        print("Run 'doc_search crawl <url>' first.")
        return 1
    
    print(f"Building index from: {pages_dir}")
    
    # Build index
    stem = not getattr(args, 'no_stemming', False)
    parser = getattr(args, 'parser', 'dom')
    index = BM25Index(k1=args.k1, b=args.b, stem=stem)
    num_docs = index.build_from_pages(pages_dir, verbose=not args.quiet, parser=parser)
    
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
    try:
        site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    except ValueError as e:
        print(style_error(f"Error: {e}"))
        return 1
    
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
        
        # Use search_enhanced() to get the dict response with metadata
        response = engine.search_enhanced(
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
            print(style_info(f'{_e("bulb")} Did you mean: "{suggestion}"?'))
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
            print(style_info(f"{_e('chart')} Facets:"))
            for ftype, values in facets.items():
                print(f"  {ftype}:")
                for value, count in sorted(values.items(), key=lambda x: -x[1])[:5]:
                    print(f"    {value}: {count}")
            print()
    
    return 0


def cmd_autocomplete(args):
    """Get autocomplete suggestions for a prefix."""
    separate_paths = getattr(args, 'separate_paths', False)
    try:
        site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    except ValueError as e:
        print(style_error(f"Error: {e}"))
        return 1
    
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
    try:
        site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    except ValueError as e:
        print(style_error(f"Error: {e}"))
        return 1
    
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
    
    # Load enhanced engine with caching
    print(style_info(f"Loading index from: {index_path}"))
    cache_path = site_dir / '.cache.db'
    engine = EnhancedSearchEngine.load(
        index_path,
        cache_size=128,
        cache_path=cache_path
    )
    
    stats = engine.get_stats()
    
    # Beautiful header
    print()
    print(style_title("╔═══════════════════════════════════════════════════════════════╗"))
    print(style_title("║") + "              " + style_success("doc-search") + " — Interactive Mode              " + style_title("║"))
    print(style_title("╚═══════════════════════════════════════════════════════════════╝"))
    print()
    print(f"  {_e('books')} {style_info(str(stats['total_documents']))} documents indexed")
    print(f"  {_e('terms')} {style_info(str(stats['unique_terms']))} unique terms")
    print(f"  {_e('ruler')} {style_info(str(stats['avg_document_length']))} avg terms per document")
    
    # Show enabled features
    features = stats.get('features', {})
    enabled = [k for k, v in features.items() if v]
    if enabled:
        print(f"  {_e('sparkles')} Features: {', '.join(enabled)}")
    
    print()
    print(style_info("  Type a query and press Enter. Empty line or Ctrl+C to exit."))
    print(style_info("  Tip: Use \"quotes\" for phrase search"))
    print(style_info("  Filters: :type pdf|html|clear  :cat <category>|clear  :filters"))
    print()
    
    prompt = f"{Colors.BRIGHT_CYAN}search>{Colors.RESET} "
    page_prompt = f"{Colors.BRIGHT_CYAN}[n]ext/[p]rev/[q]uit or new query>{Colors.RESET} "
    
    per_page = getattr(args, 'limit', 10)
    max_results = getattr(args, 'max_results', 100)
    
    # State for pagination
    current_results = []
    current_query_terms = set()
    current_suggestion = None
    current_page = 0
    elapsed_ms = 0
    
    # Filter state
    type_filter = None  # 'pdf', 'html', etc.
    category_filter = None  # URL path category
    last_query = None  # For re-running with new filters
    
    def show_page(page_num):
        """Display a single page of results."""
        start_idx = page_num * per_page
        end_idx = start_idx + per_page
        page_results = current_results[start_idx:end_idx]
        
        total_pages = (len(current_results) + per_page - 1) // per_page
        
        print()
        
        # Show active filters on first page
        if page_num == 0 and (type_filter or category_filter):
            filter_parts = []
            if type_filter:
                filter_parts.append(f"type={type_filter}")
            if category_filter:
                filter_parts.append(f"category={category_filter}")
            print(style_info(f'{_e("filter")} Filters: {", ".join(filter_parts)}'))
            print()
        
        # Show suggestion only on first page
        if page_num == 0 and current_suggestion:
            print(style_info(f'{_e("bulb")} Did you mean: "{current_suggestion}"?'))
            print()
        
        print(format_results(
            page_results, 
            show_scores=args.scores,
            query_terms=current_query_terms,
            elapsed_ms=elapsed_ms if page_num == 0 else None,
            colorize_output=True,
            start_index=start_idx
        ))
        
        # Show pagination info if there are multiple pages
        if total_pages > 1:
            print()
            print(style_info(f"  Page {page_num + 1} of {total_pages} ({len(current_results)} total results)"))
            nav_hints = []
            if page_num > 0:
                nav_hints.append("[p]rev")
            if page_num < total_pages - 1:
                nav_hints.append("[n]ext")
            nav_hints.append("[q]uit")
            print(style_info(f"  {' / '.join(nav_hints)} or type a new query"))
    
    while True:
        try:
            # Use pagination prompt if we have results to navigate
            if current_results and len(current_results) > per_page:
                user_input = input(page_prompt).strip().lower()
            else:
                user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print(style_info("\nGoodbye! 👋"))
            break
        
        if not user_input:
            print(style_info("\nGoodbye! 👋"))
            break
        
        # Handle pagination commands
        if user_input == 'n' and current_results:
            total_pages = (len(current_results) + per_page - 1) // per_page
            if current_page < total_pages - 1:
                current_page += 1
                show_page(current_page)
            else:
                print(style_info("  Already on last page"))
            continue
        elif user_input == 'p' and current_results:
            if current_page > 0:
                current_page -= 1
                show_page(current_page)
            else:
                print(style_info("  Already on first page"))
            continue
        elif user_input == 'q':
            print(style_info("\nGoodbye! 👋"))
            break
        
        # Handle filter commands
        if user_input.startswith(':type '):
            filter_val = user_input[6:].strip().lower()
            if filter_val == 'clear':
                type_filter = None
                print(style_info("  Type filter cleared"))
            elif filter_val in ('pdf', 'html'):
                type_filter = filter_val
                print(style_success(f"  Type filter set to: {type_filter}"))
            else:
                print(style_error(f"  Unknown type: {filter_val} (use pdf, html, or clear)"))
            # Re-run last query with new filter if we have one
            if last_query:
                user_input = last_query
            else:
                continue
        elif user_input.startswith(':cat '):
            filter_val = user_input[5:].strip()
            if filter_val.lower() == 'clear':
                category_filter = None
                print(style_info("  Category filter cleared"))
            else:
                category_filter = filter_val
                print(style_success(f"  Category filter set to: {category_filter}"))
            # Re-run last query with new filter if we have one
            if last_query:
                user_input = last_query
            else:
                continue
        elif user_input == ':filters':
            print(style_info(f"  Type filter: {type_filter or 'none'}"))
            print(style_info(f"  Category filter: {category_filter or 'none'}"))
            continue
        elif user_input.startswith(':'):
            print(style_error(f"  Unknown command: {user_input}"))
            print(style_info("  Commands: :type pdf|html|clear, :cat <category>|clear, :filters"))
            continue
        
        # New search query
        query = user_input
        last_query = query
        
        # Time the search (use search_enhanced for dict response with metadata)
        start_time = time.perf_counter()
        response = engine.search_enhanced(query, top_k=max_results)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        # Apply filters
        results = response['results']
        if type_filter:
            results = [r for r in results if r.get('doc_type', 'html') == type_filter]
        if category_filter:
            results = [r for r in results if r.get('facets', {}).get('category') == category_filter]
        
        current_results = results
        current_suggestion = response.get('suggestion')
        current_page = 0
        
        # Get query terms for highlighting
        terms, phrases = parse_query(query)
        current_query_terms = set(terms)
        for phrase in phrases:
            current_query_terms.update(phrase)
        
        show_page(current_page)
    
    return 0


def cmd_stats(args):
    """Show statistics for a crawled site."""
    from ..crawl_state import CrawlState
    from datetime import datetime
    
    separate_paths = getattr(args, 'separate_paths', False)
    try:
        site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    except ValueError as e:
        print(style_error(f"Error: {e}"))
        return 1
    
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
    
    # Load and display error summary from crawl state
    crawl_state_file = site_dir / 'crawl_state.json'
    if crawl_state_file.exists():
        state = CrawlState(crawl_state_file)
        if state.load():
            errors = state.get_errors()
            if errors:
                print()
                print("Crawl Errors:")
                
                # Group errors by type
                error_summary = state.get_error_summary()
                for error_type, count in sorted(error_summary.items(), key=lambda x: -x[1]):
                    print(f"  {error_type}: {count}")
                
                print(f"  Total: {len(errors)}")
                
                # Show detailed error list if --show-errors flag is set
                show_errors = getattr(args, 'show_errors', False)
                if show_errors:
                    print()
                    print("Recent Errors (last 10):")
                    # Sort by timestamp descending and take last 10
                    recent_errors = sorted(errors, key=lambda e: e.timestamp, reverse=True)[:10]
                    for error in recent_errors:
                        timestamp = datetime.fromtimestamp(error.timestamp).strftime('%Y-%m-%d %H:%M:%S')
                        # Truncate long URLs
                        url = error.url
                        if len(url) > 60:
                            url = url[:57] + '...'
                        print(f"  [{timestamp}] [{error.error_type}] {url}")
                        print(f"    {error.message}")
    
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
    try:
        site_dir = get_site_dir(args.site_dir, include_path=separate_paths)
    except ValueError as e:
        print(style_error(f"Error: {e}"))
        return 1
    
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
    
    # Load index (use EnhancedSearchEngine for spellcheck, autocomplete, facets)
    print(style_info(f"Loading index from: {index_path}"))
    enable_synonyms = getattr(args, 'synonyms', True)
    cache_size = getattr(args, 'cache_size', 128)
    cache_ttl_arg = getattr(args, 'cache_ttl', 0)
    cache_file = getattr(args, 'cache_file', None)
    # TTL of 0 means never expire (None internally)
    cache_ttl = None if cache_ttl_arg == 0 else cache_ttl_arg
    # Default cache path is <site_dir>/.cache.db, or user-specified path
    if cache_file:
        cache_path = Path(cache_file)
    elif cache_size > 0:
        cache_path = site_dir / '.cache.db'
    else:
        cache_path = None
    engine = EnhancedSearchEngine.load(
        index_path,
        enable_spellcheck=True,
        enable_autocomplete=True,
        enable_facets=True,
        enable_synonyms=enable_synonyms,
        cache_size=cache_size,
        cache_ttl=cache_ttl,
        cache_path=cache_path
    )
    
    if engine.cache_enabled:
        ttl_str = "no expiry" if cache_ttl is None else f"{cache_ttl}s TTL"
        print(style_info(f"Search cache: {cache_size} queries, {ttl_str}, persistent ({cache_path})"))
    
    stats = engine.get_stats()
    
    # Start server
    log_requests = getattr(args, 'log_requests', False)
    per_page = getattr(args, 'per_page', 10)
    max_results = getattr(args, 'max_results', 100)
    no_javascript = getattr(args, 'no_javascript', False)
    server = run_server(engine, host=args.host, port=args.port, version=__version__, 
                       log_requests=log_requests, per_page=per_page, max_results=max_results,
                       no_javascript=no_javascript)
    
    url = f"http://{args.host}:{args.port}"
    
    # Beautiful startup message
    print()
    print(style_title("╔═══════════════════════════════════════════════════════════════╗"))
    print(style_title("║") + "              " + style_success("doc-search") + " — Web UI Server                 " + style_title("║"))
    print(style_title("╚═══════════════════════════════════════════════════════════════╝"))
    print()
    print(f"  {_e('globe')} Server running at: {style_url(url)}")
    print(f"  {_e('books')} {style_info(str(stats['total_documents']))} documents indexed")
    print(f"  {_e('terms')} {style_info(str(stats['unique_terms']))} unique terms")
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
