"""
Web server for doc-search with interactive JavaScript UI.

Features instant search, keyboard navigation, and dynamic filtering.
Falls back to pure HTML/CSS with form submissions when --no-javascript is used.
Uses only Python standard library (http.server).
"""

import html
import json
import os
import re
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, List, Dict, Any

from .searcher import SearchEngine, parse_query, group_results_by_section
from .query_log import QueryLog
from . import __version__

# Emoji fallbacks for systems without emoji support
# Set DOC_SEARCH_NO_EMOJI=1 to use ASCII alternatives
_NO_EMOJI = os.environ.get('DOC_SEARCH_NO_EMOJI', '').lower() in ('1', 'true', 'yes')

_EMOJI_MAP = {
    'search': ('🔍', '[*]'),
    'docs': ('📄', '[-]'),
    'terms': ('🔤', '[#]'),
    'check': ('✓', '>'),
    'bulb': ('💡', '*'),
    'moon': ('🌙', '[D]'),
    'sun': ('☀️', '[L]'),
    'palette': ('🎨', ''),
    'books': ('📚', '[=]'),
}

def _e(name: str) -> str:
    """Get emoji or ASCII fallback based on DOC_SEARCH_NO_EMOJI env var."""
    emoji, fallback = _EMOJI_MAP.get(name, ('', ''))
    return fallback if _NO_EMOJI else emoji

# Document type icons
DOC_TYPE_ICONS = {
    'pdf': '\U0001f4c4',   # 📄
    'docx': '\U0001f4dd',  # 📝
    'xlsx': '\U0001f4ca',  # 📊
    'pptx': '\U0001f4ca',  # 📊
    'html': '\U0001f310',  # 🌐
}

def _doc_icon(doc_type: str) -> str:
    """Return emoji icon for a document type."""
    return DOC_TYPE_ICONS.get(doc_type, DOC_TYPE_ICONS['html'])


# ============================================================================
# CSS Styles - loaded from static/styles.css
# ============================================================================

_STATIC_DIR = Path(__file__).parent / 'static'
CSS = (_STATIC_DIR / 'styles.css').read_text(encoding='utf-8')


# ============================================================================
# JavaScript - loaded from static/search.js
# ============================================================================

JAVASCRIPT = (_STATIC_DIR / 'search.js').read_text(encoding='utf-8')



def escape(text: str) -> str:
    """HTML escape text."""
    return html.escape(str(text)) if text else ""


def highlight_snippet(snippet: str) -> str:
    """Convert **term** markers to <mark> elements (HTML5 semantic highlighting)."""
    if not snippet:
        return ""
    
    result = escape(snippet)
    # Replace **term** with <mark> elements
    result = re.sub(
        r'\*\*([^*]+)\*\*',
        r'<mark>\1</mark>',
        result
    )
    return result


def render_page(
    query: str = "",
    results: Optional[List[Dict[str, Any]]] = None,
    elapsed_ms: float = 0,
    stats: Optional[Dict[str, Any]] = None,
    show_scores: bool = True,
    page: int = 1,
    per_page: int = 10,
    total_results: int = 0,
    suggestion: Optional[str] = None,
    facets: Optional[Dict[str, Dict[str, int]]] = None,
    active_facet: Optional[str] = None,
    total_unfiltered: int = 0,
    sort_by: str = "relevance",
    exact_match: bool = False,
    theme: str = "dark",
    autocomplete_terms: Optional[List[str]] = None,
    global_max_score: Optional[float] = None,
    no_javascript: bool = False
) -> str:
    """Render the full HTML page."""
    
    stats = stats or {}
    total_docs = stats.get('total_documents', 0)
    unique_terms = stats.get('unique_terms', stats.get('total_unique_terms', 0))
    
    # Build datalist for HTML5 autocomplete
    datalist_html = ""
    if autocomplete_terms:
        options = "\n".join(f'        <option value="{escape(term)}">' for term in autocomplete_terms[:100])
        datalist_html = f'''
    <datalist id="search-suggestions">
{options}
    </datalist>'''
    
    # Build facet filter HTML
    facets_html = ""
    if query and facets and 'category' in facets and len(facets['category']) > 1:
        encoded_query = urllib.parse.quote(query)
        facets_html = '<div class="facet-filters"><span class="facet-label">Filter by:</span>'
        
        # "All" button - active if no facet selected
        all_class = 'facet-btn active' if not active_facet else 'facet-btn'
        all_count = total_unfiltered if total_unfiltered else total_results
        facets_html += f'<a href="/?q={encoded_query}" class="{all_class}">All <span class="facet-count">{all_count}</span></a>'
        
        # Facet buttons - sorted by count descending
        sorted_facets = sorted(facets['category'].items(), key=lambda x: -x[1])
        for facet_value, count in sorted_facets:
            is_active = active_facet == facet_value
            btn_class = 'facet-btn active' if is_active else 'facet-btn'
            facets_html += f'<a href="/?q={encoded_query}&category={urllib.parse.quote(facet_value)}" class="{btn_class}">{escape(facet_value)} <span class="facet-count">{count}</span></a>'
        
        facets_html += '</div>'
    
    # Build spell check suggestion HTML
    suggestion_html = ""
    if suggestion:
        encoded_suggestion = urllib.parse.quote(suggestion)
        suggestion_html = f'''
        <div class="spell-suggestion">
            <span class="spell-suggestion-icon">{_e('bulb')}</span>
            <span class="spell-suggestion-text">Did you mean:</span>
            <a href="/?q={encoded_suggestion}" class="spell-suggestion-link">{escape(suggestion)}</a>?
        </div>
        '''
    
    # Build results HTML
    if query and results is not None:
        if results:
            # Calculate pagination info
            total_pages = (total_results + per_page - 1) // per_page if total_results > 0 else 1
            start_num = (page - 1) * per_page + 1
            end_num = min(page * per_page, total_results)
            
            # Use global max score for normalization (so colors are consistent across pages)
            max_score = global_max_score if global_max_score else max((r.get('score', 0) for r in results), default=1) or 1
            
            results_html = f'''
            <div class="results-info">
                <span class="results-count">{_e('check')} Found {total_results} result{"s" if total_results != 1 else ""}</span>
                <span class="results-time">in {elapsed_ms:.1f}ms</span>
                <span class="results-query">showing {start_num}-{end_num} for "{escape(query)}"</span>
            </div>
            {facets_html}
            <div class="results">
            '''
            for i, r in enumerate(results, start_num):
                title = escape(r.get('title', 'Untitled') or 'Untitled')
                raw_url = r['url']
                # Convert file:// URLs to serveable /files/ URLs
                display_url = _file_url_to_serve_url(raw_url)
                url = escape(display_url)
                snippet = highlight_snippet(r.get('snippet', '') or r.get('description', ''))
                score = r.get('score', 0)
                doc_type = r.get('doc_type', 'html')
                
                # Visual score bar (normalize relative to max score in results)
                score_pct = int((score / max_score) * 100) if max_score > 0 else 0
                # Color based on confidence: green (>=70%), yellow (40-69%), red (<40%)
                if score_pct >= 70:
                    score_color = 'score-high'
                elif score_pct >= 40:
                    score_color = 'score-medium'
                else:
                    score_color = 'score-low'
                score_html = f'''<span class="result-score" title="Score: {score:.2f}">
                    <span class="result-score-bar"><span class="result-score-fill {score_color}" style="width: {score_pct}%"></span></span>
                    <span class="result-score-pct {score_color}">{score_pct}% <span style="opacity:0.5;font-size:0.85em">({score:.2f})</span></span>
                </span>''' if show_scores else ''
                
                doc_icon = _doc_icon(doc_type)
                doc_type_badge = f'<span class="doc-type-badge {doc_type}">{doc_icon} {doc_type}</span>'
                snippet_html = f'<div class="result-snippet">{snippet}</div>' if snippet else ""
                
                results_html += f'''
                <div class="result">
                    <div class="result-header">
                        <span class="result-number">{i}</span>
                        <a href="{url}" class="result-title" target="_blank" rel="noopener">{title}</a>
                        {doc_type_badge}
                        {score_html}
                    </div>
                    <div class="result-url">{escape(raw_url) if raw_url.startswith('file://') else url}</div>
                    {snippet_html}
                    <div class="result-actions">
                        {'<a href="' + url.split('#')[0] + '?download=1" class="result-action-btn" title="Download file">⬇ Download</a>' if raw_url.startswith('file://') else '<a href="' + url + '" class="result-action-btn" target="_blank" rel="noopener" title="Visit site">🔗 Visit</a>'}
                        <button class="result-action-btn copy-link-btn" data-url="{escape(raw_url) if raw_url.startswith('file://') else url}" title="Copy link">📋 Copy link</button>
                    </div>
                </div>
                '''
            results_html += '</div>'
            
            # Build pagination controls (pure HTML links)
            if total_pages > 1:
                encoded_query = urllib.parse.quote(query)
                # Preserve active facet in pagination links
                facet_param = f'&category={urllib.parse.quote(active_facet)}' if active_facet else ''
                results_html += '<div class="pagination">'
                
                # First link
                if page > 1:
                    results_html += f'<a href="/?q={encoded_query}&page=1{facet_param}">« First</a>'
                else:
                    results_html += '<span class="disabled">« First</span>'
                
                # Previous link
                if page > 1:
                    results_html += f'<a href="/?q={encoded_query}&page={page-1}{facet_param}">← Prev</a>'
                else:
                    results_html += '<span class="disabled">← Prev</span>'
                
                # Page numbers (show up to 7 pages centered on current)
                start_page = max(1, page - 3)
                end_page = min(total_pages, page + 3)
                
                if start_page > 1:
                    results_html += f'<a href="/?q={encoded_query}&page=1{facet_param}">1</a>'
                    if start_page > 2:
                        results_html += '<span class="page-info">...</span>'
                
                for p in range(start_page, end_page + 1):
                    if p == page:
                        results_html += f'<span class="current">{p}</span>'
                    else:
                        results_html += f'<a href="/?q={encoded_query}&page={p}{facet_param}">{p}</a>'
                
                if end_page < total_pages:
                    if end_page < total_pages - 1:
                        results_html += '<span class="page-info">...</span>'
                    results_html += f'<a href="/?q={encoded_query}&page={total_pages}{facet_param}">{total_pages}</a>'
                
                # Next link
                if page < total_pages:
                    results_html += f'<a href="/?q={encoded_query}&page={page+1}{facet_param}">Next →</a>'
                else:
                    results_html += '<span class="disabled">Next →</span>'
                
                # Last link
                if page < total_pages:
                    results_html += f'<a href="/?q={encoded_query}&page={total_pages}{facet_param}">Last »</a>'
                else:
                    results_html += '<span class="disabled">Last »</span>'
                
                results_html += '</div>'
        else:
            results_html = suggestion_html + f'''
            <div class="no-results">
                <div class="no-results-icon">{_e('search')}</div>
                <div>No results found. Try different keywords.</div>
            </div>
            '''
    else:
        # Welcome state
        results_html = f'''
        <div class="welcome">
            <div class="welcome-icon">{_e('books')}</div>
            <div class="welcome-title">Search Documentation</div>
            <div class="welcome-description">
                Enter your search query above to find relevant documentation pages.
            </div>
        </div>
        <div class="tips">
            <div class="tips-title">{_e('bulb')} Search tips</div>
            <div class="tips-list">
                <div class="tip">Use quotes for exact phrases: <code>"list comprehension"</code></div>
                <div class="tip">Combine terms: <code>async await python</code></div>
            </div>
        </div>
        '''
    
    # Build search options HTML
    sort_relevance_sel = 'selected' if sort_by == 'relevance' else ''
    sort_date_sel = 'selected' if sort_by == 'date' else ''
    limit_10_sel = 'selected' if per_page == 10 else ''
    limit_25_sel = 'selected' if per_page == 25 else ''
    limit_50_sel = 'selected' if per_page == 50 else ''
    exact_checked = 'checked' if exact_match else ''
    body_class = 'light' if theme == 'light' else ''
    
    # Build theme toggle URLs (preserve current query params)
    theme_params = []
    if query:
        theme_params.append(f"q={urllib.parse.quote(query)}")
    if sort_by != "relevance":
        theme_params.append(f"sort={sort_by}")
    if per_page != 10:
        theme_params.append(f"limit={per_page}")
    if exact_match:
        theme_params.append("exact=1")
    if active_facet:
        theme_params.append(f"category={urllib.parse.quote(active_facet)}")
    base_params = "&".join(theme_params)
    # light_url used for no-JS fallback toggle (switches theme via page reload)
    light_url = "/?" + (base_params + "&theme=light" if base_params else "theme=light") if theme == "dark" else "/?" + (base_params + "&theme=dark" if base_params else "theme=dark")
    
    search_options_html = f'''
            <div class="search-options">
                <div class="search-option">
                    <label for="sort">Sort:</label>
                    <select name="sort" id="sort">
                        <option value="relevance" {sort_relevance_sel}>Relevance</option>
                        <option value="date" {sort_date_sel}>Newest</option>
                    </select>
                </div>
                <div class="search-option limit-option">
                    <label for="limit">Results:</label>
                    <select name="limit" id="limit">
                        <option value="10" {limit_10_sel}>10</option>
                        <option value="25" {limit_25_sel}>25</option>
                        <option value="50" {limit_50_sel}>50</option>
                    </select>
                </div>
                <div class="search-option">
                    <label>
                        <input type="checkbox" name="exact" value="1" {exact_checked}>
                        Exact match
                    </label>
                </div>
                <div class="theme-toggle">
                    <span class="theme-toggle-label">{_e('moon')}</span>
                    <a href="{light_url}" class="theme-switch {theme}" title="Toggle theme">
                        <span class="theme-switch-knob"></span>
                    </a>
                    <span class="theme-toggle-label">{_e('sun')}</span>
                </div>
            </div>
    '''
    
    # JavaScript block (only if not disabled)
    js_html = '' if no_javascript else f'<script>{JAVASCRIPT}</script>'
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{"Search: " + escape(query) + " — " if query else ""}doc-search</title>
    <style>{CSS}</style>
</head>
<body class="{body_class}">
    <header class="header">
        <div class="header-content">
            <a href="/" class="logo">
                <span class="logo-icon">{_e('search')}</span>
                <span>doc-search</span>
            </a>
            <span class="version">v{__version__}</span>
        </div>
    </header>
    
    <main class="main">
        <form class="search-form" method="GET" action="/">
            <div class="search-box">
                <div class="search-input-wrapper">
                    <input 
                        type="text" 
                        name="q"
                        class="search-input" 
                        placeholder="Search documentation..."
                        value="{escape(query)}"
                        list="search-suggestions"
                        autocomplete="off"
                        minlength="1"
                        maxlength="200"
                        accesskey="s"
                        autofocus
                    >
                    <button type="button" class="search-clear" aria-label="Clear search">✕</button>
                </div>
                <button type="submit" class="search-button">Search</button>
            </div>
            {search_options_html}
        </form>
        {datalist_html}
        
        {results_html}
    </main>
    
    <footer class="footer">
        <div class="footer-stats">
            <div class="stat">
                <span>{_e('docs')}</span>
                <span class="stat-value">{total_docs:,}</span>
                <span>documents</span>
            </div>
            <div class="stat">
                <span>{_e('terms')}</span>
                <span class="stat-value">{unique_terms:,}</span>
                <span>terms</span>
            </div>
        </div>
        <div>doc-search v{__version__}</div>
    </footer>
{js_html}
</body>
</html>'''


def _file_url_to_serve_url(url: str) -> str:
    """Convert file:// URL to /files/ proxy URL for browser access."""
    if url.startswith('file://'):
        # Split off fragment (e.g., #page=3)
        base, _, fragment = url[7:].partition('#')
        encoded = urllib.parse.quote(base, safe='/')
        result = f"/files/{encoded}"
        if fragment:
            result += f"#{fragment}"
        return result
    return url


class SearchHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the search web UI."""
    
    engine: SearchEngine = None
    version: str = ""
    log_requests: bool = False
    per_page: int = 10
    max_results: int = 100
    start_time: float = None  # Server start time for uptime calculation
    enable_autocomplete: bool = True  # Enable /suggest endpoint
    enable_facets: bool = True  # Enable faceted search filtering
    enable_synonyms: bool = False  # Enable synonym expansion toggle
    no_javascript: bool = False  # Serve pure HTML/CSS UI without JavaScript
    query_log: QueryLog = None  # Optional query logging

    def log_message(self, format, *args):
        """Log HTTP requests if enabled."""
        if self.log_requests:
            message = format % args
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {self.address_string()} - {message}")
    
    def handle(self):
        """Handle a connection, suppressing broken pipe errors."""
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Client disconnected mid-request (common with instant search)
    
    def finish(self):
        """Finish a connection, suppressing broken pipe errors."""
        try:
            super().finish()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Client already disconnected
    
    def send_html(self, content: str, status: int = 200):
        """Send HTML response."""
        try:
            body = content.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Client disconnected (e.g., browser aborted request)
    
    def send_json(self, data: dict, status: int = 200):
        """Send JSON response."""
        try:
            body = json.dumps(data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Client disconnected (e.g., browser aborted request)
    
    @staticmethod
    def file_url_to_serve_url(url: str) -> str:
        """Convert file:// URL to /files/ proxy URL for browser access."""
        return _file_url_to_serve_url(url)

    def do_GET(self):
        """Handle GET requests."""
        import inspect
        
        parsed = urllib.parse.urlparse(self.path)
        
        # Handle /health endpoint
        if parsed.path == '/health':
            self.handle_health()
            return
        
        # Handle /suggest endpoint for autocomplete
        if parsed.path == '/suggest':
            self.handle_suggest(parsed.query)
            return
        
        # Handle /api/search endpoint for instant search (JSON)
        if parsed.path == '/api/search':
            self.handle_api_search(parsed.query)
            return
        
        # Handle /files/ endpoint for serving local documents
        if parsed.path.startswith('/files/'):
            self.handle_serve_file(parsed.path[7:], parsed.query)
            return
        
        query_params = urllib.parse.parse_qs(parsed.query)
        
        # Get search query
        query = query_params.get('q', [''])[0].strip()
        
        # Get page number (default 1, minimum 1)
        try:
            page = max(1, int(query_params.get('page', ['1'])[0]))
        except ValueError:
            page = 1
        
        # Get facet filter (category)
        category_filter = query_params.get('category', [''])[0].strip() if self.enable_facets else ''
        
        # Get search options
        sort_by = query_params.get('sort', ['relevance'])[0]
        if sort_by not in ('relevance', 'date'):
            sort_by = 'relevance'
        
        # Get results limit (per page)
        try:
            per_page = int(query_params.get('limit', [str(self.per_page)])[0])
            if per_page not in (10, 25, 50):
                per_page = self.per_page
        except ValueError:
            per_page = self.per_page
        
        # Get exact match toggle
        exact_match = query_params.get('exact', [''])[0] == '1'
        
        # Get theme
        theme = query_params.get('theme', ['dark'])[0]
        if theme not in ('dark', 'light'):
            theme = 'dark'
        
        max_results = self.max_results
        
        # Get stats
        stats = self.engine.get_stats() if self.engine else {}
        
        if query:
            # Perform search - fetch enough for pagination
            search_start = time.perf_counter()
            
            # For exact match, wrap query in quotes for phrase matching
            # (unless it's already quoted)
            search_query = query
            if exact_match and not (query.startswith('"') and query.endswith('"')):
                search_query = f'"{query}"'
            
            # Pass expand_synonyms if enabled and engine supports it
            # Exact match disables synonym expansion
            use_synonyms = self.enable_synonyms and not exact_match
            if use_synonyms and hasattr(self.engine, 'search'):
                sig = inspect.signature(self.engine.search)
                if 'expand_synonyms' in sig.parameters:
                    all_results = self.engine.search(search_query, top_k=max_results, expand_synonyms=True)
                else:
                    all_results = self.engine.search(search_query, top_k=max_results)
            else:
                all_results = self.engine.search(search_query, top_k=max_results)
            elapsed_ms = (time.perf_counter() - search_start) * 1000

            if self.query_log:
                self.query_log.log(query, len(all_results), elapsed_ms)

            # Get facet counts before filtering (for accurate counts)
            facets = None
            total_unfiltered = len(all_results)
            if self.enable_facets and hasattr(self.engine, 'get_facet_counts'):
                facets = self.engine.get_facet_counts(all_results)
            
            # Apply facet filter if specified
            filtered_results = all_results
            if category_filter and facets and 'category' in facets:
                filtered_results = [
                    r for r in all_results 
                    if r.get('facets', {}).get('category') == category_filter
                ]
            
            total_results = len(filtered_results)
            
            # Sort by date if requested
            if sort_by == 'date' and hasattr(self.engine, 'pages_dir') and self.engine.pages_dir:
                filtered_results = self._sort_by_date(filtered_results)
            
            # Slice for current page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_results = filtered_results[start_idx:end_idx]
            
            # If page is beyond results, redirect to page 1
            if not page_results and total_results > 0:
                page = 1
                page_results = filtered_results[:per_page]
            
            # Get spelling suggestion from search engine
            # With two-pass architecture, suggestion is generated during search
            # and stored in last_suggestion (display only - user must click to use)
            suggestion = None
            if hasattr(self.engine, 'last_suggestion'):
                suggestion = self.engine.last_suggestion
            elif total_results == 0 and hasattr(self.engine, 'get_spelling_suggestion'):
                # Fallback for basic search engine
                suggestion = self.engine.get_spelling_suggestion(query)
                if suggestion and suggestion.lower() == query.lower():
                    suggestion = None
            
            # Get autocomplete terms for datalist
            autocomplete_terms = None
            if self.enable_autocomplete and hasattr(self.engine, 'get_autocomplete_suggestions'):
                # Get suggestions based on query for refinement
                if query:
                    autocomplete_terms = self.engine.get_autocomplete_suggestions(query[:3], max_suggestions=50)
            
            # Get global max score for consistent color normalization across pages
            global_max = filtered_results[0].get('score', 1) if filtered_results else 1
            
            html_content = render_page(
                query=query,
                results=page_results,
                elapsed_ms=elapsed_ms,
                stats=stats,
                page=page,
                per_page=per_page,
                total_results=total_results,
                suggestion=suggestion,
                facets=facets,
                active_facet=category_filter if category_filter else None,
                total_unfiltered=total_unfiltered,
                sort_by=sort_by,
                exact_match=exact_match,
                theme=theme,
                autocomplete_terms=autocomplete_terms,
                global_max_score=global_max,
                no_javascript=self.no_javascript
            )
        else:
            # Welcome page
            theme = query_params.get('theme', ['dark'])[0]
            if theme not in ('dark', 'light'):
                theme = 'dark'
            
            # Get popular terms for datalist on welcome page
            autocomplete_terms = None
            if self.enable_autocomplete and hasattr(self.engine, 'get_autocomplete_suggestions'):
                # Get general suggestions for empty search
                autocomplete_terms = self.engine.get_autocomplete_suggestions('', max_suggestions=100)
            
            html_content = render_page(stats=stats, theme=theme, autocomplete_terms=autocomplete_terms, no_javascript=self.no_javascript)
        
        self.send_html(html_content)
    
    def _sort_by_date(self, results):
        """Sort results by crawled_at date (newest first)."""
        import json as _json
        from .utils import url_to_filename
        
        pages_dir = self.engine.pages_dir
        if not pages_dir:
            return results
        
        def get_date(r):
            url = r.get('url', '')
            filename = url_to_filename(url) + '.json'
            filepath = pages_dir / filename
            try:
                with open(filepath, encoding='utf-8') as f:
                    data = _json.load(f)
                return data.get('crawled_at', 0)
            except Exception:
                return 0
        
        return sorted(results, key=get_date, reverse=True)
    
    def do_POST(self):
        """Handle POST requests."""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/api/click':
            self.handle_api_click()
            return

        self.send_error(404)

    def handle_api_click(self):
        """Log a click on a search result."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception:
            self.send_json({'error': 'invalid request'}, 400)
            return

        if self.query_log:
            import sqlite3
            with self.query_log._lock:
                self.query_log._conn.execute(
                    'CREATE TABLE IF NOT EXISTS click_log ('
                    '  id INTEGER PRIMARY KEY AUTOINCREMENT,'
                    '  query TEXT, url TEXT, rank INTEGER, timestamp REAL'
                    ')'
                )
                self.query_log._conn.execute(
                    'INSERT INTO click_log (query, url, rank, timestamp) VALUES (?, ?, ?, ?)',
                    (data.get('query', ''), data.get('url', ''),
                     data.get('rank', 0), time.time())
                )
                self.query_log._conn.commit()

        self.send_json({'ok': True})

    def handle_suggest(self, query_string: str):
        """Handle /suggest endpoint for autocomplete suggestions.
        
        Returns JSON: {"suggestions": ["term1", "term2", ...]}
        Query params:
            q: prefix to get suggestions for
            limit: maximum number of suggestions (default 5, max 20)
        """
        # Check if autocomplete is enabled
        if not self.enable_autocomplete:
            self.send_json({'error': 'Autocomplete is disabled'}, 403)
            return
        
        # Check if engine supports autocomplete
        if not hasattr(self.engine, 'get_autocomplete_suggestions'):
            self.send_json({'error': 'Autocomplete not available'}, 501)
            return
        
        # Parse query parameters
        query_params = urllib.parse.parse_qs(query_string)
        prefix = query_params.get('q', [''])[0].strip()
        
        # Get limit (default 5, max 20)
        try:
            limit = min(20, max(1, int(query_params.get('limit', ['5'])[0])))
        except ValueError:
            limit = 5
        
        if not prefix:
            self.send_json({'suggestions': []})
            return
        
        try:
            # Use title suggestions if available (richer results)
            if hasattr(self.engine, 'get_title_suggestions'):
                title_results = self.engine.get_title_suggestions(prefix, limit)
                self.send_json({'suggestions': title_results})
            else:
                suggestions = self.engine.get_autocomplete_suggestions(prefix, limit)
                self.send_json({'suggestions': [
                    {'text': s, 'doc_type': None, 'url': None} for s in suggestions
                ]})
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    def handle_api_search(self, query_string: str):
        """Handle /api/search endpoint for instant search (JSON response).
        
        Returns JSON with search results for JavaScript-driven UI.
        Query params:
            q: search query
            page: page number (default 1)
            limit: results per page (10, 25, or 50)
            category: facet filter
            exact: 1 for exact match
            sort: relevance or date
        """
        import inspect
        
        query_params = urllib.parse.parse_qs(query_string)
        
        # Get search query
        query = query_params.get('q', [''])[0].strip()
        
        if not query:
            self.send_json({
                'query': '',
                'results': [],
                'total': 0,
                'total_unfiltered': 0,
                'page': 1,
                'per_page': self.per_page,
                'total_pages': 1,
                'elapsed_ms': 0,
                'suggestion': None,
                'facets': None,
                'active_facet': None,
                'global_max_score': 0
            })
            return
        
        # Get page number (default 1, minimum 1)
        try:
            page = max(1, int(query_params.get('page', ['1'])[0]))
        except ValueError:
            page = 1
        
        # Get facet filters (category and type)
        category_filter = query_params.get('category', [''])[0].strip() if self.enable_facets else ''
        type_filter = query_params.get('type', [''])[0].strip() if self.enable_facets else ''
        
        # Get results limit (per page)
        try:
            per_page = int(query_params.get('limit', [str(self.per_page)])[0])
            if per_page not in (10, 25, 50):
                per_page = self.per_page
        except ValueError:
            per_page = self.per_page
        
        # Get exact match toggle
        exact_match = query_params.get('exact', [''])[0] == '1'
        output_format = query_params.get('format', ['json'])[0]
        group_by_section = query_params.get('group', [''])[0] == '1'

        max_results = self.max_results

        try:
            # Perform search
            search_start = time.perf_counter()
            
            # For exact match, wrap query in quotes
            search_query = query
            if exact_match and not (query.startswith('"') and query.endswith('"')):
                search_query = f'"{query}"'
            
            # Pass expand_synonyms if enabled
            use_synonyms = self.enable_synonyms and not exact_match
            if use_synonyms and hasattr(self.engine, 'search'):
                sig = inspect.signature(self.engine.search)
                if 'expand_synonyms' in sig.parameters:
                    all_results = self.engine.search(search_query, top_k=max_results, expand_synonyms=True)
                else:
                    all_results = self.engine.search(search_query, top_k=max_results)
            else:
                all_results = self.engine.search(search_query, top_k=max_results)
            elapsed_ms = (time.perf_counter() - search_start) * 1000

            if self.query_log:
                self.query_log.log(query, len(all_results), elapsed_ms)

            # Get facet counts with cross-filtering
            # When type is filtered, category facets only count items of that type
            # When category is filtered, type facets only count items in that category
            facets = None
            total_unfiltered = len(all_results)
            
            # Apply filters and compute cross-filtered facet counts
            filtered_results = all_results
            
            # Filter by type first if specified
            if type_filter:
                filtered_results = [
                    r for r in filtered_results 
                    if r.get('doc_type', 'html') == type_filter
                ]
            
            # Filter by category if specified
            if category_filter:
                filtered_results = [
                    r for r in filtered_results 
                    if r.get('facets', {}).get('category') == category_filter
                ]
            
            # Compute facets from the filtered results (cross-filtered counts)
            if self.enable_facets:
                # Type facets: count from category-filtered results (or all if no category filter)
                type_base = [r for r in all_results if r.get('facets', {}).get('category') == category_filter] if category_filter else all_results
                type_counts = {}
                for r in type_base:
                    doc_type = r.get('doc_type', 'html')
                    type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
                
                # Category facets: count from type-filtered results (or all if no type filter)
                cat_base = [r for r in all_results if r.get('doc_type', 'html') == type_filter] if type_filter else all_results
                cat_counts = {}
                for r in cat_base:
                    category = r.get('facets', {}).get('category')
                    if category:
                        cat_counts[category] = cat_counts.get(category, 0) + 1
                
                facets = {
                    'type': type_counts if len(type_counts) > 1 else {},
                    'category': cat_counts if len(cat_counts) > 1 else {}
                }
            
            total_results = len(filtered_results)
            
            # Sort by date if requested
            sort_by = query_params.get('sort', ['relevance'])[0]
            if sort_by == 'date' and hasattr(self.engine, 'pages_dir') and self.engine.pages_dir:
                filtered_results = self._sort_by_date(filtered_results)
            
            # Apply section grouping if requested
            if group_by_section:
                filtered_results = group_results_by_section(filtered_results, max_per_group=3)
                total_results = len(filtered_results)

            # Slice for current page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_results = filtered_results[start_idx:end_idx]

            # Get spelling suggestion from search engine
            # With two-pass architecture, suggestion is generated during search
            suggestion = None
            if hasattr(self.engine, 'last_suggestion'):
                suggestion = self.engine.last_suggestion
            elif total_results == 0 and hasattr(self.engine, 'get_spelling_suggestion'):
                # Fallback for basic search engine
                suggestion = self.engine.get_spelling_suggestion(query)
                if suggestion and suggestion.lower() == query.lower():
                    suggestion = None
            
            # Calculate max score for normalization
            global_max_score = filtered_results[0].get('score', 1) if filtered_results else 1
            
            # Format results for JSON
            json_results = []
            start_num = (page - 1) * per_page + 1
            for i, r in enumerate(page_results, start_num):
                score = r.get('score', 0)
                score_pct = int((score / global_max_score) * 100) if global_max_score > 0 else 0
                
                url = r['url']
                # Convert file:// URLs to serveable /files/ URLs
                serve_url = self.file_url_to_serve_url(url)
                
                json_results.append({
                    'rank': i,
                    'title': r.get('title', 'Untitled') or 'Untitled',
                    'url': serve_url,
                    'original_url': url if url != serve_url else None,
                    'snippet': r.get('snippet', '') or r.get('description', ''),
                    'score': round(score, 4),
                    'score_pct': score_pct,
                    'facets': r.get('facets', {}),
                    'doc_type': r.get('doc_type', 'html'),
                    'section': r.get('section')
                })
            
            # Build response
            response = {
                'query': query,
                'results': json_results,
                'total': total_results,
                'total_unfiltered': total_unfiltered,
                'page': page,
                'per_page': per_page,
                'total_pages': (total_results + per_page - 1) // per_page if total_results > 0 else 1,
                'elapsed_ms': round(elapsed_ms, 2),
                'suggestion': suggestion,
                'facets': facets,
                'active_facet': category_filter if category_filter else None,
                'active_type': type_filter if type_filter else None,
                'global_max_score': round(global_max_score, 4)
            }
            
            if output_format == 'csv':
                import csv
                import io
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(['url', 'title', 'score', 'snippet'])
                for jr in json_results:
                    writer.writerow([
                        jr.get('original_url') or jr['url'],
                        jr['title'],
                        jr['score'],
                        jr.get('snippet', '')
                    ])
                body = buf.getvalue().encode('utf-8')
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/csv; charset=utf-8')
                    self.send_header('Content-Disposition', 'attachment; filename="results.csv"')
                    self.send_header('Content-Length', len(body))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            self.send_json(response)

        except Exception as e:
            self.send_json({'error': str(e)}, 500)

    def handle_serve_file(self, encoded_path: str, query_string: str = ''):
        """Serve a local file referenced by file:// URL.
        
        Query params:
            download=1: Force download instead of inline display
        
        Only serves files that exist in the index (source_file metadata)
        to prevent arbitrary file access.
        """
        import mimetypes
        
        file_path = urllib.parse.unquote(encoded_path)
        query_params = urllib.parse.parse_qs(query_string)
        force_download = query_params.get('download', [''])[0] == '1'
        
        # Security: resolve to absolute path and check for traversal
        try:
            resolved = Path(file_path).resolve()
        except (ValueError, OSError):
            self.send_error(400, "Invalid path")
            return
        
        if not resolved.is_file():
            self.send_error(404, "File not found")
            return
        
        # Security: only serve file types we index
        allowed_extensions = {'.pdf', '.docx', '.xlsx', '.pptx', '.html', '.htm'}
        if resolved.suffix.lower() not in allowed_extensions:
            self.send_error(403, "File type not allowed")
            return
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(str(resolved))
        if not content_type:
            content_type = 'application/octet-stream'
        
        try:
            file_size = resolved.stat().st_size
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', file_size)
            # Force download or try inline display
            if force_download:
                self.send_header('Content-Disposition', f'attachment; filename="{resolved.name}"')
            else:
                self.send_header('Content-Disposition', f'inline; filename="{resolved.name}"')
            self.end_headers()
            
            with open(resolved, 'rb') as f:
                # Stream in 64KB chunks
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Client disconnected
        except IOError as e:
            self.send_error(500, f"Error reading file: {e}")

    def handle_health(self):
        """Handle /health endpoint for monitoring and load balancers."""
        try:
            # Get index stats
            stats = self.engine.get_stats() if self.engine else {}
            
            # Calculate uptime
            uptime_seconds = 0
            if self.start_time:
                uptime_seconds = time.time() - self.start_time
            
            # Build health response
            health_data = {
                'status': 'ok',
                'documents': stats.get('total_documents', 0),
                'terms': stats.get('unique_terms', stats.get('total_unique_terms', 0)),
                'uptime_seconds': round(uptime_seconds, 1),
                'version': self.version or __version__
            }
            
            # Determine if healthy (has at least some documents indexed)
            is_healthy = stats.get('total_documents', 0) > 0
            status_code = 200 if is_healthy else 503
            
            if not is_healthy:
                health_data['status'] = 'unhealthy'
                health_data['reason'] = 'No documents indexed'
            
            self.send_json(health_data, status_code)
            
        except Exception as e:
            # On error, return 503
            error_data = {
                'status': 'unhealthy',
                'error': str(e)
            }
            self.send_json(error_data, 503)


def run_server(
    engine: SearchEngine,
    host: str = '127.0.0.1',
    port: int = 8888,
    version: str = "",
    log_requests: bool = False,
    per_page: int = 10,
    max_results: int = 100,
    enable_autocomplete: bool = True,
    enable_facets: bool = True,
    enable_synonyms: bool = False,
    no_javascript: bool = False,
    query_log: QueryLog = None
) -> HTTPServer:
    """Create and return the HTTP server (doesn't start it).
    
    Args:
        engine: The SearchEngine instance to use for queries
        host: Host address to bind to
        port: Port number to listen on
        version: Version string to display
        log_requests: If True, log HTTP requests to stdout
        per_page: Number of results per page (default: 10)
        max_results: Maximum total results for pagination (default: 100)
        enable_autocomplete: If True, enable /suggest endpoint (default: True)
        enable_facets: If True, enable faceted search filtering (default: True)
        enable_synonyms: If True, show synonym expansion toggle (default: False)
        no_javascript: If True, serve pure HTML/CSS UI without JavaScript
        
    Returns:
        HTTPServer instance (call serve_forever() to start)
    """
    SearchHandler.engine = engine
    SearchHandler.version = version
    SearchHandler.log_requests = log_requests
    SearchHandler.per_page = per_page
    SearchHandler.max_results = max_results
    SearchHandler.start_time = time.time()  # Record server start time
    SearchHandler.enable_facets = enable_facets
    SearchHandler.enable_autocomplete = enable_autocomplete
    SearchHandler.enable_synonyms = enable_synonyms
    SearchHandler.no_javascript = no_javascript
    SearchHandler.query_log = query_log
    server = HTTPServer((host, port), SearchHandler)
    return server
