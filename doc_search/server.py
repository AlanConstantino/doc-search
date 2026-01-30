"""
Web server for doc-search with pure HTML/CSS interface.

No JavaScript - all server-side rendering with form submissions.
Uses only Python standard library (http.server).
"""

import html
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, List, Dict, Any

from .searcher import SearchEngine, parse_query
from . import __version__


# ============================================================================
# CSS Styles - Beautiful dark theme, pure CSS
# ============================================================================

CSS = """
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --border: #30363d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-muted: #6e7681;
    --accent: #58a6ff;
    --accent-hover: #79c0ff;
    --highlight-bg: rgba(88, 166, 255, 0.15);
    --highlight-text: #79c0ff;
    --success: #3fb950;
    --warning: #d29922;
    --gradient-start: #58a6ff;
    --gradient-end: #a371f7;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    min-height: 100vh;
}

a {
    color: var(--accent);
    text-decoration: none;
}

a:hover {
    color: var(--accent-hover);
    text-decoration: underline;
}

/* Header */
.header {
    background: var(--bg-secondary);
    border-bottom: 1px solid var(--border);
    padding: 1rem 0;
}

.header-content {
    max-width: 900px;
    margin: 0 auto;
    padding: 0 1.5rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.logo {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
}

.logo:hover {
    text-decoration: none;
    color: var(--text-primary);
}

.logo-icon {
    font-size: 1.5rem;
}

.version {
    font-size: 0.75rem;
    color: var(--text-muted);
    background: var(--bg-tertiary);
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
}

/* Main content */
.main {
    max-width: 900px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
}

/* Search form */
.search-form {
    margin-bottom: 2rem;
}

.search-box {
    display: flex;
    gap: 0.75rem;
}

.search-input {
    flex: 1;
    padding: 0.875rem 1rem;
    font-size: 1.125rem;
    background: var(--bg-secondary);
    border: 2px solid var(--border);
    border-radius: 10px;
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
}

.search-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--highlight-bg);
}

.search-input::placeholder {
    color: var(--text-muted);
}

.search-button {
    padding: 0.875rem 1.5rem;
    font-size: 1rem;
    font-weight: 600;
    background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
    border: none;
    border-radius: 10px;
    color: white;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
}

.search-button:hover {
    opacity: 0.9;
}

.search-button:active {
    transform: scale(0.98);
}

/* Results info */
.results-info {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1.25rem;
    font-size: 0.9rem;
}

.results-count {
    color: var(--success);
    font-weight: 600;
}

.results-time {
    color: var(--text-muted);
}

.results-query {
    color: var(--text-secondary);
    font-style: italic;
}

/* Results list */
.results {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.result {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    transition: border-color 0.2s, background 0.2s;
}

.result:hover {
    border-color: var(--accent);
    background: var(--bg-tertiary);
}

.result-header {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
}

.result-number {
    background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
    color: white;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
    min-width: 1.75rem;
    text-align: center;
}

.result-title {
    flex: 1;
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--accent);
    line-height: 1.3;
}

.result-title:hover {
    color: var(--accent-hover);
}

.result-score {
    background: var(--bg-tertiary);
    color: var(--warning);
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
    font-family: monospace;
}

.result-url {
    font-size: 0.8125rem;
    color: var(--text-muted);
    margin-bottom: 0.75rem;
    word-break: break-all;
}

.result-snippet {
    font-size: 0.9375rem;
    color: var(--text-secondary);
    line-height: 1.6;
}

.highlight {
    background: var(--highlight-bg);
    color: var(--highlight-text);
    padding: 0.1em 0.25em;
    border-radius: 3px;
    font-weight: 600;
}

/* Empty/welcome state */
.welcome {
    text-align: center;
    padding: 4rem 2rem;
}

.welcome-icon {
    font-size: 4rem;
    margin-bottom: 1rem;
    opacity: 0.7;
}

.welcome-title {
    font-size: 1.5rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
}

.welcome-description {
    color: var(--text-secondary);
    max-width: 400px;
    margin: 0 auto 1.5rem;
}

/* No results */
.no-results {
    text-align: center;
    padding: 3rem 2rem;
    color: var(--text-secondary);
}

.no-results-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
    opacity: 0.5;
}

/* Tips */
.tips {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem;
    margin-top: 2rem;
}

.tips-title {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 0.75rem;
}

.tips-list {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
}

.tip {
    font-size: 0.875rem;
    color: var(--text-secondary);
}

.tip code {
    background: var(--bg-tertiary);
    padding: 0.15em 0.4em;
    border-radius: 4px;
    font-size: 0.8125rem;
    color: var(--accent);
}

/* Footer */
.footer {
    max-width: 900px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
    border-top: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 1rem;
    font-size: 0.8125rem;
    color: var(--text-muted);
}

.footer-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
}

.stat {
    display: flex;
    align-items: center;
    gap: 0.35rem;
}

.stat-value {
    color: var(--text-secondary);
    font-weight: 600;
}
"""


def escape(text: str) -> str:
    """HTML escape text."""
    return html.escape(str(text)) if text else ""


def highlight_snippet(snippet: str) -> str:
    """Convert **term** markers to <span class="highlight">."""
    if not snippet:
        return ""
    
    result = escape(snippet)
    # Replace **term** with highlighted spans
    import re
    result = re.sub(
        r'\*\*([^*]+)\*\*',
        r'<span class="highlight">\1</span>',
        result
    )
    return result


def render_page(
    query: str = "",
    results: Optional[List[Dict[str, Any]]] = None,
    elapsed_ms: float = 0,
    stats: Optional[Dict[str, Any]] = None,
    show_scores: bool = True
) -> str:
    """Render the full HTML page."""
    
    stats = stats or {}
    total_docs = stats.get('total_documents', 0)
    unique_terms = stats.get('unique_terms', 0)
    
    # Build results HTML
    if query and results is not None:
        if results:
            results_html = f'''
            <div class="results-info">
                <span class="results-count">✓ Found {len(results)} result{"s" if len(results) != 1 else ""}</span>
                <span class="results-time">in {elapsed_ms:.1f}ms</span>
                <span class="results-query">for "{escape(query)}"</span>
            </div>
            <div class="results">
            '''
            for i, r in enumerate(results, 1):
                title = escape(r.get('title', 'Untitled') or 'Untitled')
                url = escape(r['url'])
                snippet = highlight_snippet(r.get('snippet', '') or r.get('description', ''))
                score = r.get('score', 0)
                
                score_html = f'<span class="result-score">{score:.2f}</span>' if show_scores else ''
                
                results_html += f'''
                <div class="result">
                    <div class="result-header">
                        <span class="result-number">{i}</span>
                        <a href="{url}" class="result-title" target="_blank" rel="noopener">{title}</a>
                        {score_html}
                    </div>
                    <div class="result-url">{url}</div>
                    {"<div class='result-snippet'>" + snippet + "</div>" if snippet else ""}
                </div>
                '''
            results_html += '</div>'
        else:
            results_html = '''
            <div class="no-results">
                <div class="no-results-icon">🔍</div>
                <div>No results found. Try different keywords.</div>
            </div>
            '''
    else:
        # Welcome state
        results_html = '''
        <div class="welcome">
            <div class="welcome-icon">📚</div>
            <div class="welcome-title">Search Documentation</div>
            <div class="welcome-description">
                Enter your search query above to find relevant documentation pages.
            </div>
        </div>
        <div class="tips">
            <div class="tips-title">💡 Search tips</div>
            <div class="tips-list">
                <div class="tip">Use quotes for exact phrases: <code>"list comprehension"</code></div>
                <div class="tip">Combine terms: <code>async await python</code></div>
            </div>
        </div>
        '''
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{"Search: " + escape(query) + " — " if query else ""}doc-search</title>
    <style>{CSS}</style>
</head>
<body>
    <header class="header">
        <div class="header-content">
            <a href="/" class="logo">
                <span class="logo-icon">🔍</span>
                <span>doc-search</span>
            </a>
            <span class="version">v{__version__}</span>
        </div>
    </header>
    
    <main class="main">
        <form class="search-form" method="GET" action="/">
            <div class="search-box">
                <input 
                    type="text" 
                    name="q"
                    class="search-input" 
                    placeholder="Search documentation..."
                    value="{escape(query)}"
                    autofocus
                >
                <button type="submit" class="search-button">Search</button>
            </div>
        </form>
        
        {results_html}
    </main>
    
    <footer class="footer">
        <div class="footer-stats">
            <div class="stat">
                <span>📄</span>
                <span class="stat-value">{total_docs:,}</span>
                <span>documents</span>
            </div>
            <div class="stat">
                <span>🔤</span>
                <span class="stat-value">{unique_terms:,}</span>
                <span>terms</span>
            </div>
        </div>
        <div>doc-search v{__version__}</div>
    </footer>
</body>
</html>'''


class SearchHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the search web UI."""
    
    engine: SearchEngine = None
    version: str = ""
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def send_html(self, content: str, status: int = 200):
        """Send HTML response."""
        body = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed.query)
        
        # Get search query
        query = query_params.get('q', [''])[0].strip()
        
        # Get stats
        stats = self.engine.get_stats() if self.engine else {}
        
        if query:
            # Perform search
            start_time = time.perf_counter()
            results = self.engine.search(query, top_k=20)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            html_content = render_page(
                query=query,
                results=results,
                elapsed_ms=elapsed_ms,
                stats=stats
            )
        else:
            # Welcome page
            html_content = render_page(stats=stats)
        
        self.send_html(html_content)


def run_server(
    engine: SearchEngine,
    host: str = '127.0.0.1',
    port: int = 8888,
    version: str = ""
) -> HTTPServer:
    """Create and return the HTTP server (doesn't start it)."""
    SearchHandler.engine = engine
    SearchHandler.version = version
    server = HTTPServer((host, port), SearchHandler)
    return server
