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

import atexit
import getpass
import json
import os
import time
from pathlib import Path
from typing import Optional, Tuple

# readline enables command history (up/down arrows) in interactive mode
# Not available on all platforms (e.g., Windows without pyreadline)
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

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
    'skip': ('⏭', '-'),
}

def _e(name: str) -> str:
    """Get emoji or ASCII fallback based on DOC_SEARCH_NO_EMOJI env var."""
    emoji, fallback = _EMOJI_MAP.get(name, ('', ''))
    return fallback if _NO_EMOJI else emoji


# Default data directory
DEFAULT_DATA_DIR = Path.home() / '.doc_search' / 'sites'


def get_site_dir(url_or_path: str, include_path: bool = False) -> Path:
    """Get site data directory from URL, existing path, or hash.
    
    Args:
        url_or_path: URL, existing directory path, or site hash
        include_path: If True, include URL path in hash (separate storage per path)
    
    Returns:
        Path to the site data directory
    
    Raises:
        ValueError: If input is not a valid URL, existing directory, or known hash
    
    Hash lookup supports:
        - Full hash: "a1b2c3d4e5f6" → looks for files_a1b2c3d4e5f6 or site_a1b2c3d4e5f6
        - With prefix: "files_a1b2c3d4e5f6" → direct lookup
    """
    # Check if it's a URL (http:// or https://)
    if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
        return DEFAULT_DATA_DIR / site_hash(url_or_path, include_path=include_path)
    
    # Check if it's a hash (alphanumeric, typically 12 chars)
    # Support both raw hash and prefixed versions (files_xxx, site_xxx)
    if url_or_path.replace('_', '').replace('-', '').isalnum():
        # Try various prefixes
        candidates = []
        
        if url_or_path.startswith('files_') or url_or_path.startswith('site_'):
            # Already has prefix
            candidates.append(DEFAULT_DATA_DIR / url_or_path)
        else:
            # Try with common prefixes
            candidates.append(DEFAULT_DATA_DIR / f"files_{url_or_path}")
            candidates.append(DEFAULT_DATA_DIR / f"site_{url_or_path}")
            # Also try as-is (might be a full directory name)
            candidates.append(DEFAULT_DATA_DIR / url_or_path)
        
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
    
    # Not a URL or hash - check if it's an existing directory path
    path = Path(url_or_path)
    
    # Check if path exists
    if not path.exists():
        raise ValueError(
            f"Directory not found: {url_or_path}\n"
            f"If this is a URL, it must start with http:// or https://\n"
            f"If this is a hash, ensure the site exists in {DEFAULT_DATA_DIR}\n"
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
    
    # Count total pages and doc types on disk for accurate metadata
    pages_dir = site_dir / 'pages'
    total_pages = 0
    doc_type_counts = {}
    if pages_dir.exists():
        for page_file in pages_dir.glob('*.json'):
            total_pages += 1
            try:
                with open(page_file) as pf:
                    page_data = json.load(pf)
                doc_type = page_data.get('doc_type', 'html')
            except (json.JSONDecodeError, IOError):
                doc_type = 'html'
            doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
    else:
        total_pages = stats.get('pages_crawled', 0)
    
    # Calculate total site size on disk
    site_size = sum(f.stat().st_size for f in site_dir.rglob('*') if f.is_file())
    
    # Save site metadata
    metadata = {
        'url': args.url,
        'stats': {**stats, 'pages_crawled': total_pages},
        'doc_type_counts': doc_type_counts,
        'site_size_bytes': site_size
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
    
    stem = not getattr(args, 'no_stemming', False)
    parser = getattr(args, 'parser', 'dom')
    full_rebuild = getattr(args, 'full', False)
    
    # Try incremental indexing if not forced full and existing index available
    existing_index = None
    if not full_rebuild:
        for candidate in [site_dir / 'index.json.gz', site_dir / 'index.json']:
            if candidate.exists():
                try:
                    existing_index = BM25Index.load(candidate)
                    # Check if params match; if not, force full rebuild
                    if existing_index.k1 != args.k1 or existing_index.b != args.b or existing_index.stem != stem:
                        if not args.quiet:
                            print("Index parameters changed, performing full rebuild...")
                        existing_index = None
                except Exception:
                    existing_index = None
                break
    
    if existing_index is not None and existing_index.content_hashes:
        # Incremental update
        if not args.quiet:
            print("Performing incremental index update...")
        index = existing_index
        incr_stats = index.build_from_pages_incremental(pages_dir, verbose=not args.quiet, parser=parser)
        num_docs = index.total_docs
    else:
        # Full rebuild
        if not args.quiet:
            if not full_rebuild and existing_index is not None:
                print("No content hashes in existing index, performing full rebuild...")
            print("Performing full index build...")
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
    
    # Build and save fuzzy search index (SymSpell)
    no_symspell = getattr(args, 'no_symspell', False)
    if not no_symspell:
        if not args.quiet:
            print(f"\nBuilding SymSpell index...")
        
        symspell = index.build_symspell(max_distance=2)
        fuzzy_path = symspell.save(str(site_dir / 'fuzzy'), compress=not args.no_compress)
        
        stats = symspell.get_stats()
        print(f"SymSpell index saved to: {fuzzy_path}")
        print(f"SymSpell index: {stats['word_count']} words, {stats['unique_deletes']} deletion entries")
    
    # Build and save n-gram index for prefix/substring search
    no_ngram = getattr(args, 'no_ngram', False)
    if not no_ngram:
        if not args.quiet:
            print(f"\nBuilding n-gram index...")
        
        ngram_index = index.build_ngram_index(n=3)
        ngram_path = ngram_index.save(str(site_dir / 'ngram'), compress=not args.no_compress)
        
        stats = ngram_index.get_stats()
        print(f"N-gram index saved to: {ngram_path}")
        print(f"N-gram index: {stats['term_count']} terms, {stats['ngram_count']} trigrams")
    
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
            enable_symspell=not getattr(args, 'no_symspell', False),
            enable_ngram=not getattr(args, 'no_ngram', False),
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
        cache_path=cache_path,
        enable_symspell=not getattr(args, 'no_symspell', False),
        enable_ngram=not getattr(args, 'no_ngram', False)
    )
    
    stats = engine.get_stats()
    
    # Beautiful header
    print()
    print(style_title("╔═══════════════════════════════════════════════════════════════╗"))
    print(style_title("║") + "              " + style_success("doc-search") + " — Interactive Mode              " + style_title("║"))
    print(style_title("╚═══════════════════════════════════════════════════════════════╝"))
    print()
    print(f"  {_e('books')} {style_info(str(stats.get('total_documents', 0)))} documents indexed")
    print(f"  {_e('terms')} {style_info(str(stats.get('unique_terms', stats.get('total_unique_terms', 0))))} unique terms")
    print(f"  {_e('ruler')} {style_info(str(stats.get('avg_document_length', 0)))} avg terms per document")
    
    # Show enabled features
    features = stats.get('features', {})
    enabled = [k for k, v in features.items() if v]
    if enabled:
        print(f"  {_e('sparkles')} Features: {', '.join(enabled)}")
    
    print()
    print(style_info("  Type a query and press Enter. Empty line or Ctrl+C to exit."))
    print(style_info("  Tip: Use \"quotes\" for phrase search"))
    print(style_info("  Filters: :type pdf|web|docx|xlsx|clear  :cat <category>|clear  :filters"))
    if READLINE_AVAILABLE:
        print(style_info("  History: Use ↑/↓ arrow keys to cycle through previous commands"))
        print(style_info("  Tab: Press Tab for autocomplete suggestions"))
    print()
    
    # Set up command history and tab completion with readline
    if READLINE_AVAILABLE:
        history_file = site_dir / '.history'
        try:
            readline.read_history_file(history_file)
        except FileNotFoundError:
            pass  # No history file yet, that's fine
        readline.set_history_length(100)  # Keep last 100 commands
        atexit.register(readline.write_history_file, history_file)
        
        # Tab completion using autocomplete suggestions
        if hasattr(engine, 'get_autocomplete_suggestions'):
            def completer(text, state):
                if state == 0:
                    # Get the full input line and cursor position
                    line = readline.get_line_buffer()
                    # Use the last word as the prefix for completion
                    words = line.split()
                    prefix = words[-1] if words else ''
                    if prefix:
                        suggestions = engine.get_autocomplete_suggestions(prefix, max_suggestions=15)
                        # Build completions: replace just the last word
                        completer._matches = [s + ' ' for s in suggestions if s.startswith(prefix)]
                    else:
                        completer._matches = []
                try:
                    return completer._matches[state]
                except IndexError:
                    return None
            
            completer._matches = []
            readline.set_completer(completer)
            readline.set_completer_delims(' \t')
            readline.parse_and_bind('tab: complete')
    
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
            else:
                # Normalize aliases
                type_aliases = {'web': 'html', 'word': 'docx', 'excel': 'xlsx'}
                normalized = type_aliases.get(filter_val, filter_val)
                if normalized in ('pdf', 'html', 'docx', 'xlsx'):
                    type_filter = normalized
                    display_labels = {'html': 'web', 'pdf': 'pdf', 'docx': 'docx', 'xlsx': 'xlsx'}
                    print(style_success(f"  Type filter set to: {display_labels[type_filter]}"))
                else:
                    print(style_error(f"  Unknown type: {filter_val} (use pdf, html/web, docx/word, xlsx/excel, or clear)"))
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


def _scan_doc_type_counts(pages_dir: Path) -> dict:
    """Scan page files to build doc_type_counts. Slow but accurate."""
    type_counts = {}
    if not pages_dir.exists():
        return type_counts
    for page_file in pages_dir.glob('*.json'):
        try:
            with open(page_file) as pf:
                page_data = json.load(pf)
            doc_type = page_data.get('doc_type', 'html')
        except (json.JSONDecodeError, IOError):
            doc_type = 'html'
        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
    return type_counts


def cmd_list(args):
    """List all crawled sites."""
    if not DEFAULT_DATA_DIR.exists():
        print("No sites crawled yet.")
        return 0
    
    sites = list(DEFAULT_DATA_DIR.iterdir())
    if not sites:
        print("No sites crawled yet.")
        return 0
    
    refresh = getattr(args, 'refresh', False)
    
    print(f"Crawled sites ({len(sites)}):")
    print()
    
    for site_dir in sorted(sites):
        if not site_dir.is_dir():
            continue
        
        metadata_file = site_dir / 'metadata.json'
        if metadata_file.exists():
            with open(metadata_file) as f:
                metadata = json.load(f)
            url = metadata.get('url') or metadata.get('source') or metadata.get('site_name') or 'Unknown'
            
            pages_dir = site_dir / 'pages'
            
            if refresh:
                # Rebuild doc type counts and size from page files
                type_counts = _scan_doc_type_counts(pages_dir)
                total_pages = sum(type_counts.values()) if type_counts else 0
                site_size = sum(f.stat().st_size for f in site_dir.rglob('*') if f.is_file())
                # Update metadata cache
                metadata['doc_type_counts'] = type_counts
                metadata['site_size_bytes'] = site_size
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
            else:
                # Use cached doc_type_counts from metadata (fast path)
                type_counts = metadata.get('doc_type_counts', {})
                if type_counts:
                    total_pages = sum(type_counts.values())
                elif pages_dir.exists():
                    # Fallback: just count files (no JSON parsing)
                    total_pages = sum(1 for _ in pages_dir.glob('*.json'))
                else:
                    total_pages = metadata.get('stats', {}).get('pages_crawled', 0)
            
            # Build display string
            is_files = metadata.get('type') == 'files'
            label = 'docs' if is_files else 'pages'
            if len(type_counts) > 1:
                type_parts = []
                for dtype in sorted(type_counts.keys()):
                    count = type_counts[dtype]
                    type_parts.append(f"{count} {dtype}")
                type_str = f"{total_pages} {label}: {', '.join(type_parts)}"
            else:
                type_str = f"{total_pages} {label}"
            
            print(f"  {site_dir.name}: {url} ({type_str})")
        else:
            print(f"  {site_dir.name}: (no metadata)")
    
    print()
    print(f"Data directory: {DEFAULT_DATA_DIR}")
    
    return 0


def cmd_delete(args):
    """Delete crawled site(s) and their indexes."""
    import shutil
    
    dry_run = getattr(args, 'dry_run', False)
    delete_all = getattr(args, 'all', False)
    site_ids = getattr(args, 'site', None) or []
    
    if not DEFAULT_DATA_DIR.exists():
        print("No sites crawled yet.")
        return 0
    
    sites_to_delete = []
    
    if delete_all:
        # Delete all sites
        for site_dir in DEFAULT_DATA_DIR.iterdir():
            if site_dir.is_dir():
                sites_to_delete.append(site_dir)
    elif site_ids:
        not_found = []
        for site_id in site_ids:
            found = False
            
            # First, check if it's a direct hash match
            direct_match = DEFAULT_DATA_DIR / site_id
            if direct_match.exists() and direct_match.is_dir():
                sites_to_delete.append(direct_match)
                found = True
            
            # If not a direct hash, check if it's a URL
            if not found and (site_id.startswith('http://') or site_id.startswith('https://')):
                # Try to find by URL hash
                url_hash = site_hash(site_id, include_path=False)
                hash_match = DEFAULT_DATA_DIR / url_hash
                if hash_match.exists() and hash_match.is_dir():
                    sites_to_delete.append(hash_match)
                    found = True
                else:
                    # Also try with include_path=True
                    url_hash_path = site_hash(site_id, include_path=True)
                    hash_path_match = DEFAULT_DATA_DIR / url_hash_path
                    if hash_path_match.exists() and hash_path_match.is_dir():
                        sites_to_delete.append(hash_path_match)
                        found = True
            
            # If still not found, search metadata files for matching URL
            if not found:
                for site_dir in DEFAULT_DATA_DIR.iterdir():
                    if not site_dir.is_dir():
                        continue
                    metadata_file = site_dir / 'metadata.json'
                    if metadata_file.exists():
                        with open(metadata_file) as f:
                            metadata = json.load(f)
                        url = metadata.get('url', '')
                        # Match if the site_id is contained in the URL or matches the hash
                        if site_id in url or site_dir.name.startswith(site_id):
                            sites_to_delete.append(site_dir)
                            found = True
                            break
            
            if not found:
                not_found.append(site_id)
        
        if not_found:
            for nf in not_found:
                print(style_error(f"Error: Site not found: {nf}"))
            if not sites_to_delete:
                print()
                print("Use 'doc_search list' to see available sites.")
                print("You can specify sites by URL or hash ID.")
                return 1
            print()
    else:
        print(style_error("Error: Must specify one or more sites or use --all"))
        return 1
    
    if not sites_to_delete:
        print("No sites to delete.")
        return 0
    
    # Show what will be deleted
    print(f"{'Would delete' if dry_run else 'Deleting'} {len(sites_to_delete)} site(s):")
    print()
    
    total_size = 0
    for site_dir in sites_to_delete:
        # Get site info
        metadata = {}
        metadata_file = site_dir / 'metadata.json'
        if metadata_file.exists():
            with open(metadata_file) as f:
                metadata = json.load(f)
            url = metadata.get('url') or metadata.get('source') or 'Unknown'
            pages = metadata.get('stats', {}).get('pages_crawled', 0)
        else:
            url = "(no metadata)"
            pages = 0
        
        # Use cached size from metadata, fall back to calculation for dry run
        site_size = metadata.get('site_size_bytes', 0)
        if site_size == 0 and dry_run:
            site_size = sum(f.stat().st_size for f in site_dir.rglob('*') if f.is_file())
        total_size += site_size
        
        size_str = f", {format_size(site_size)}" if site_size else ""
        
        if dry_run:
            print(f"  {_e('cross')} {site_dir.name}")
            print(f"    URL: {url}")
            print(f"    Pages: {pages}{size_str}")
        else:
            print(f"  {_e('cross')} {site_dir.name}: {url} ({pages} pages{size_str})")
            shutil.rmtree(site_dir)
    
    print()
    if dry_run:
        size_note = f" ({format_size(total_size)})" if total_size else ""
        print(style_info(f"Dry run: Would delete {len(sites_to_delete)} site(s){size_note}"))
        print(style_info("Run without --dry-run to actually delete."))
    else:
        size_note = f", freed ~{format_size(total_size)}" if total_size else ""
        print(style_success(f"{_e('check')} Deleted {len(sites_to_delete)} site(s){size_note}"))
    
    return 0


def cmd_index_files(args):
    """Index local documents (.xlsx, .docx, .pdf)."""
    from ..excel_extractor import ExcelExtractor
    from ..word_extractor import WordExtractor
    from ..pdf_extractor import PDFExtractor
    import hashlib
    
    directory = Path(args.directory)
    if not directory.exists():
        print(style_error(f"Error: Directory not found: {directory}"))
        return 1
    
    if not directory.is_dir():
        print(style_error(f"Error: Not a directory: {directory}"))
        return 1
    
    # Parse extensions
    extensions_str = getattr(args, 'extensions', 'xlsx,docx,pdf')
    extensions = set('.' + ext.strip().lower().lstrip('.') for ext in extensions_str.split(','))
    
    # Determine site name and directory
    site_name = getattr(args, 'site_name', None) or directory.name
    
    # Create site directory with meaningful name: files_<dirname>_<short_hash>
    # Sanitize directory name (remove special chars, limit length)
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', directory.name)[:30].strip('_')
    if not safe_name:
        safe_name = 'files'
    dir_hash = hashlib.sha256(str(directory.absolute()).encode()).hexdigest()[:8]
    site_dir = DEFAULT_DATA_DIR / f"files_{safe_name}_{dir_hash}"
    
    # Check for merge
    merge_with = getattr(args, 'merge_with', None)
    if merge_with:
        try:
            merge_site_dir = get_site_dir(merge_with)
            if merge_site_dir.exists():
                site_dir = merge_site_dir
                print(style_info(f"Merging with existing site: {merge_site_dir}"))
        except ValueError:
            print(style_error(f"Error: Cannot find site to merge with: {merge_with}"))
            return 1
    
    site_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = site_dir / 'pages'
    pages_dir.mkdir(exist_ok=True)
    
    # Load file cache for incremental indexing
    cache_file = site_dir / '.file_cache.json'
    file_cache = {}
    force_reindex = getattr(args, 'force', False)
    clean_stale = getattr(args, 'clean', False)
    
    if not force_reindex and cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                file_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            file_cache = {}
    
    print(f"Indexing: {directory}")
    print(f"Extensions: {', '.join(sorted(extensions))}")
    print(f"Data directory: {site_dir}")
    if force_reindex:
        print(style_info("Force mode: re-indexing all files"))
    elif file_cache:
        print(style_info(f"Incremental mode: {len(file_cache)} files in cache"))
    print()
    
    # Set up extractors
    first_row_is_header = not getattr(args, 'no_headers', False)
    max_rows = getattr(args, 'max_rows', None)
    excel_extractor = ExcelExtractor(
        first_row_is_header=first_row_is_header,
        max_rows=max_rows
    )
    word_extractor = WordExtractor()
    pdf_extractor = PDFExtractor()
    
    # Find and process files
    recursive = not getattr(args, 'no_recursive', False)
    exclude_patterns = getattr(args, 'exclude', []) or []
    
    files_found = 0
    docs_extracted = 0
    docs_by_type = {}  # Track per-type counts: {'pdf': N, 'docx': N, 'xlsx': N}
    errors = 0
    
    # Collect files
    if recursive:
        all_files = list(directory.rglob('*'))
    else:
        all_files = list(directory.glob('*'))
    
    # Filter to supported extensions
    files_to_process = []
    for f in all_files:
        if not f.is_file():
            continue
        if f.suffix.lower() not in extensions:
            continue
        # Check exclude patterns
        excluded = False
        for pattern in exclude_patterns:
            if f.match(pattern):
                excluded = True
                break
        if not excluded:
            files_to_process.append(f)
    
    files_found = len(files_to_process)
    
    # Track which files we've seen for stale detection
    seen_files = set()
    skipped = 0
    
    # Helper to check if file has changed
    def file_changed(fp: Path) -> bool:
        """Check if file has changed since last indexing."""
        if force_reindex:
            return True
        
        file_key = str(fp.absolute())
        if file_key not in file_cache:
            return True
        
        cached = file_cache[file_key]
        stat = fp.stat()
        
        # Check mtime and size (fast check)
        if stat.st_mtime != cached.get('mtime') or stat.st_size != cached.get('size'):
            return True
        
        return False
    
    # Helper to update cache entry
    def update_cache(fp: Path, doc_ids: list):
        """Update cache entry for a file."""
        stat = fp.stat()
        file_cache[str(fp.absolute())] = {
            'mtime': stat.st_mtime,
            'size': stat.st_size,
            'doc_ids': doc_ids,
            'indexed_at': time.time()
        }
    
    print(f"Found {files_found} files to check...")
    print()
    
    quiet = getattr(args, 'quiet', False)
    
    for file_path in files_to_process:
        ext = file_path.suffix.lower()
        seen_files.add(str(file_path.absolute()))
        
        # Skip unchanged files
        if not file_changed(file_path):
            skipped += 1
            if not quiet:
                print(f"  {_e('skip')} {file_path.name} (unchanged)")
            continue
        
        try:
            if ext == '.xlsx':
                documents = excel_extractor.extract(file_path)
            elif ext == '.docx':
                documents = word_extractor.extract(file_path)
            elif ext == '.pdf':
                # Extract PDF as one document per page for better search granularity
                documents = pdf_extractor.extract_pages_from_file(file_path)
            else:
                # Skip unsupported extensions
                continue
            
            # Save each document and track doc_ids for cache
            file_doc_ids = []
            for doc in documents:
                if doc.get('error'):
                    if not quiet:
                        print(style_error(f"  {_e('cross')} {file_path.name}: {doc['error']}"))
                    errors += 1
                    continue
                
                # Generate document ID from URL
                doc_id = hashlib.sha256(doc['url'].encode()).hexdigest()[:16]
                file_doc_ids.append(doc_id)
                
                # Save as JSON (same format as crawled pages)
                doc_file = pages_dir / f"{doc_id}.json"
                
                # Convert headings tuples to lists for JSON
                doc_json = {
                    'url': doc['url'],
                    'title': doc['title'],
                    'text': doc['text'],
                    'headings': [list(h) for h in doc.get('headings', [])],
                    'doc_type': doc.get('metadata', {}).get('doc_type', 'unknown'),
                    **{k: v for k, v in doc.get('metadata', {}).items() if k != 'doc_type'}
                }
                
                with open(doc_file, 'w', encoding='utf-8') as f:
                    json.dump(doc_json, f, ensure_ascii=False, indent=2)
                
                docs_extracted += 1
                doc_type_key = ext.lstrip('.')
                docs_by_type[doc_type_key] = docs_by_type.get(doc_type_key, 0) + 1
                
                if not quiet:
                    print(f"  {_e('check')} {doc['title'][:60]}")
            
            # Update cache for this file
            if file_doc_ids:
                update_cache(file_path, file_doc_ids)
        
        except Exception as e:
            if not quiet:
                print(style_error(f"  {_e('cross')} {file_path.name}: {e}"))
            errors += 1
    
    # Clean stale documents (files that no longer exist)
    stale_removed = 0
    if clean_stale:
        stale_files = set(file_cache.keys()) - seen_files
        for stale_file in stale_files:
            cached = file_cache[stale_file]
            for doc_id in cached.get('doc_ids', []):
                doc_file = pages_dir / f"{doc_id}.json"
                if doc_file.exists():
                    doc_file.unlink()
                    stale_removed += 1
            del file_cache[stale_file]
        if stale_removed and not quiet:
            print(style_info(f"Removed {stale_removed} stale documents from {len(stale_files)} deleted files"))
    
    # Save the file cache
    with open(cache_file, 'w') as f:
        json.dump(file_cache, f, indent=2)
    
    print()
    processed = files_found - skipped
    print(f"Processed {processed} files, skipped {skipped} unchanged")
    if docs_by_type:
        type_labels = {'pdf': 'PDFs', 'docx': 'Word docs', 'xlsx': 'Excel sheets'}
        type_parts = []
        for dtype in sorted(docs_by_type.keys()):
            label = type_labels.get(dtype, dtype)
            type_parts.append(f"{docs_by_type[dtype]} {label}")
        print(f"Extracted {docs_extracted} documents ({', '.join(type_parts)})")
    else:
        print(f"Extracted {docs_extracted} documents")
    if errors:
        print(style_error(f"Errors: {errors}"))
    
    # Count doc types from extracted pages for fast listing
    doc_type_counts = {}
    if pages_dir.exists():
        for page_file in pages_dir.glob('*.json'):
            try:
                with open(page_file) as pf:
                    page_data = json.load(pf)
                doc_type = page_data.get('doc_type', 'unknown')
            except (json.JSONDecodeError, IOError):
                doc_type = 'unknown'
            doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
    
    # Calculate total site size on disk
    site_size = sum(f.stat().st_size for f in site_dir.rglob('*') if f.is_file())
    
    # Save metadata
    metadata = {
        'source': str(directory.absolute()),
        'site_name': site_name,
        'type': 'files',
        'stats': {
            'files_found': files_found,
            'docs_extracted': docs_extracted,
            'errors': errors,
            'extensions': list(extensions)
        },
        'doc_type_counts': doc_type_counts,
        'site_size_bytes': site_size
    }
    with open(site_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nDocuments saved to: {pages_dir}")
    print(f"Run 'doc_search index {site_dir}' to build the search index")
    
    return 0


def cmd_search_all(args):
    """Search across all crawled sites."""
    from ..multi_search import MultiSiteSearchEngine
    
    site_filters = getattr(args, 'sites', None)
    
    engine = MultiSiteSearchEngine(site_filters=site_filters)
    
    if engine.site_count == 0:
        print(style_error("Error: No indexed sites found."))
        print("Run 'doc_search crawl <url>' and 'doc_search index <url>' first.")
        return 1
    
    if not args.quiet and not args.json:
        print(style_info(f"Searching across {engine.site_count} site(s)..."))
    
    # Time the search
    start_time = time.perf_counter()
    results = engine.search(
        args.query,
        top_k=args.limit,
        highlight=True,
        snippet_length=150,
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    # Get query terms for highlighting
    terms, phrases = parse_query(args.query)
    query_terms = set(terms)
    for phrase in phrases:
        query_terms.update(phrase)
    
    if args.json:
        output = {
            'query': args.query,
            'elapsed_ms': round(elapsed_ms, 2),
            'sites_searched': engine.site_count,
            'count': len(results),
            'results': results,
        }
        print(json.dumps(output, indent=2))
    else:
        print()
        if results:
            for i, r in enumerate(results, 1):
                site_label = r.get('site', 'unknown')
                score_str = f" [{r['score']:.4f}]" if args.scores else ""
                print(f"  {i}. {style_title(r.get('title', 'Untitled'))}{score_str}")
                print(f"     {style_url(r['url'])}")
                print(f"     {_e('globe')} {style_info(site_label)}")
                if r.get('snippet'):
                    print(f"     {r['snippet']}")
                print()
            print(style_info(f"  {len(results)} result(s) across {engine.site_count} site(s) ({elapsed_ms:.1f}ms)"))
        else:
            print(style_info("  No results found."))
        print()
    
    return 0


def cmd_serve(args):
    """Start the web UI server for searching."""
    import webbrowser
    from ..server import run_server
    
    multi_site = getattr(args, 'all', False)
    
    if multi_site:
        # Multi-site mode: use MultiSiteSearchEngine wrapped as a SearchEngine-like object
        from ..multi_search import MultiSiteSearchEngine
        
        site_filters = getattr(args, 'sites', None)
        multi_engine = MultiSiteSearchEngine(site_filters=site_filters)
        
        if multi_engine.site_count == 0:
            print(style_error("Error: No indexed sites found."))
            return 1
        
        print(style_info(f"Multi-site mode: {multi_engine.site_count} site(s)"))
        for s in multi_engine.sites:
            print(style_info(f"  - {s.get('url') or s['name']}"))
        
        engine = multi_engine
        stats = multi_engine.get_stats()
        site_dir = DEFAULT_DATA_DIR
    else:
        if not args.site_dir:
            print(style_error("Error: site_dir is required (or use --all for multi-site mode)"))
            return 1
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
            enable_symspell=not getattr(args, 'no_symspell', False),
            enable_ngram=not getattr(args, 'no_ngram', False),
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
    print(f"  {_e('books')} {style_info(str(stats.get('total_documents', 0)))} documents indexed")
    print(f"  {_e('terms')} {style_info(str(stats.get('unique_terms', stats.get('total_unique_terms', 0))))} unique terms")
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
