"""
Web server for doc-search with beautiful UI.

Uses only Python standard library (http.server).
"""

import json
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Any

from .searcher import SearchEngine, parse_query


# ============================================================================
# Beautiful HTML/CSS/JS - All embedded in one file
# ============================================================================

HTML_TEMPLATE = r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>doc-search</title>
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --bg-hover: #30363d;
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
        
        [data-theme="light"] {
            --bg-primary: #ffffff;
            --bg-secondary: #f6f8fa;
            --bg-tertiary: #eaeef2;
            --bg-hover: #d0d7de;
            --border: #d0d7de;
            --text-primary: #1f2328;
            --text-secondary: #57606a;
            --text-muted: #6e7781;
            --accent: #0969da;
            --accent-hover: #0550ae;
            --highlight-bg: rgba(9, 105, 218, 0.1);
            --highlight-text: #0550ae;
            --success: #1a7f37;
            --warning: #9a6700;
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
        
        /* Header */
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 1rem 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        
        .header-content {
            max-width: 900px;
            margin: 0 auto;
            padding: 0 1.5rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
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
        
        .logo-icon {
            font-size: 1.5rem;
        }
        
        .theme-toggle {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.5rem 0.75rem;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.2s;
        }
        
        .theme-toggle:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
        }
        
        /* Main content */
        .main {
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem 1.5rem;
        }
        
        /* Search box */
        .search-container {
            margin-bottom: 2rem;
        }
        
        .search-box {
            position: relative;
        }
        
        .search-input {
            width: 100%;
            padding: 1rem 1rem 1rem 3rem;
            font-size: 1.125rem;
            background: var(--bg-secondary);
            border: 2px solid var(--border);
            border-radius: 12px;
            color: var(--text-primary);
            outline: none;
            transition: all 0.2s;
        }
        
        .search-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 4px var(--highlight-bg);
        }
        
        .search-input::placeholder {
            color: var(--text-muted);
        }
        
        .search-icon {
            position: absolute;
            left: 1rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            font-size: 1.25rem;
            pointer-events: none;
        }
        
        .search-shortcut {
            position: absolute;
            right: 1rem;
            top: 50%;
            transform: translateY(-50%);
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 0.25rem 0.5rem;
            font-size: 0.75rem;
            color: var(--text-muted);
            font-family: monospace;
        }
        
        /* Results info */
        .results-info {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }
        
        .results-count {
            color: var(--success);
            font-weight: 600;
        }
        
        .results-time {
            color: var(--text-muted);
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
            transition: all 0.2s;
            cursor: pointer;
        }
        
        .result:hover, .result.selected {
            border-color: var(--accent);
            background: var(--bg-tertiary);
        }
        
        .result.selected {
            box-shadow: 0 0 0 2px var(--highlight-bg);
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
            min-width: 1.5rem;
            text-align: center;
        }
        
        .result-title {
            flex: 1;
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--accent);
            text-decoration: none;
            line-height: 1.3;
        }
        
        .result-title:hover {
            color: var(--accent-hover);
            text-decoration: underline;
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
        
        .result-snippet mark {
            background: var(--highlight-bg);
            color: var(--highlight-text);
            padding: 0.1em 0.25em;
            border-radius: 3px;
            font-weight: 600;
        }
        
        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: var(--text-secondary);
        }
        
        .empty-icon {
            font-size: 4rem;
            margin-bottom: 1rem;
            opacity: 0.5;
        }
        
        .empty-title {
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 0.5rem;
        }
        
        .empty-description {
            max-width: 400px;
            margin: 0 auto;
        }
        
        /* Tips */
        .tips {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-top: 2rem;
        }
        
        .tips-title {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .tips-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 0.75rem;
        }
        
        .tip {
            display: flex;
            align-items: center;
            gap: 0.5rem;
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
        
        /* Keyboard hints */
        .keyboard-hints {
            position: fixed;
            bottom: 1rem;
            right: 1rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        
        .keyboard-hints kbd {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 0.1rem 0.35rem;
            font-family: monospace;
            margin: 0 0.1rem;
        }
        
        /* Loading */
        .loading {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            color: var(--text-muted);
        }
        
        .spinner {
            width: 1.5rem;
            height: 1.5rem;
            border: 2px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 0.75rem;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <header class="header">
        <div class="header-content">
            <a href="/" class="logo">
                <span class="logo-icon">🔍</span>
                <span>doc-search</span>
            </a>
            <button class="theme-toggle" id="themeToggle" title="Toggle theme">
                🌙
            </button>
        </div>
    </header>
    
    <main class="main">
        <div class="search-container">
            <div class="search-box">
                <span class="search-icon">🔎</span>
                <input 
                    type="text" 
                    class="search-input" 
                    id="searchInput"
                    placeholder="Search documentation..."
                    autocomplete="off"
                    autofocus
                >
                <span class="search-shortcut">/</span>
            </div>
        </div>
        
        <div id="resultsInfo" class="results-info" style="display: none;"></div>
        
        <div id="results" class="results"></div>
        
        <div id="emptyState" class="empty-state">
            <div class="empty-icon">📚</div>
            <div class="empty-title">Start searching</div>
            <div class="empty-description">
                Type your query above to search through the documentation.
            </div>
        </div>
        
        <div class="tips" id="tips">
            <div class="tips-title">
                <span>💡</span>
                <span>Search tips</span>
            </div>
            <div class="tips-list">
                <div class="tip">
                    <span>Exact phrases:</span>
                    <code>"list comprehension"</code>
                </div>
                <div class="tip">
                    <span>Navigate:</span>
                    <code>j</code> / <code>k</code> or <code>↑</code> / <code>↓</code>
                </div>
                <div class="tip">
                    <span>Open result:</span>
                    <code>Enter</code> or <code>o</code>
                </div>
                <div class="tip">
                    <span>Focus search:</span>
                    <code>/</code>
                </div>
            </div>
        </div>
    </main>
    
    <footer class="footer">
        <div class="footer-stats" id="footerStats">
            <div class="stat">
                <span>📄</span>
                <span class="stat-value" id="statDocs">-</span>
                <span>documents</span>
            </div>
            <div class="stat">
                <span>🔤</span>
                <span class="stat-value" id="statTerms">-</span>
                <span>terms</span>
            </div>
        </div>
        <div>
            doc-search v{{VERSION}}
        </div>
    </footer>
    
    <div class="keyboard-hints">
        <kbd>j</kbd>/<kbd>k</kbd> navigate
        <kbd>Enter</kbd> open
        <kbd>/</kbd> search
        <kbd>Esc</kbd> clear
    </div>

    <script>
        // State
        let results = [];
        let selectedIndex = -1;
        let searchTimeout = null;
        let stats = null;
        
        // DOM elements
        const searchInput = document.getElementById('searchInput');
        const resultsDiv = document.getElementById('results');
        const resultsInfo = document.getElementById('resultsInfo');
        const emptyState = document.getElementById('emptyState');
        const tips = document.getElementById('tips');
        const themeToggle = document.getElementById('themeToggle');
        
        // Theme handling
        function getPreferredTheme() {
            const stored = localStorage.getItem('theme');
            if (stored) return stored;
            return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
        }
        
        function setTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            themeToggle.textContent = theme === 'light' ? '🌙' : '☀️';
        }
        
        setTheme(getPreferredTheme());
        
        themeToggle.addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme') || 'dark';
            setTheme(current === 'light' ? 'dark' : 'light');
        });
        
        // Fetch stats on load
        async function fetchStats() {
            try {
                const response = await fetch('/api/stats');
                stats = await response.json();
                document.getElementById('statDocs').textContent = stats.total_documents.toLocaleString();
                document.getElementById('statTerms').textContent = stats.unique_terms.toLocaleString();
            } catch (e) {
                console.error('Failed to fetch stats:', e);
            }
        }
        fetchStats();
        
        // Search function
        async function search(query) {
            if (!query.trim()) {
                results = [];
                selectedIndex = -1;
                renderResults();
                return;
            }
            
            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=20`);
                const data = await response.json();
                
                results = data.results || [];
                selectedIndex = results.length > 0 ? 0 : -1;
                
                renderResults(data.elapsed_ms, data.count);
            } catch (e) {
                console.error('Search failed:', e);
            }
        }
        
        // Render results
        function renderResults(elapsedMs, count) {
            if (results.length === 0) {
                resultsDiv.innerHTML = '';
                resultsInfo.style.display = 'none';
                emptyState.style.display = searchInput.value.trim() ? 'block' : 'block';
                tips.style.display = searchInput.value.trim() ? 'none' : 'block';
                
                if (searchInput.value.trim()) {
                    emptyState.innerHTML = `
                        <div class="empty-icon">🔍</div>
                        <div class="empty-title">No results found</div>
                        <div class="empty-description">
                            Try different keywords or check your spelling.
                        </div>
                    `;
                } else {
                    emptyState.innerHTML = `
                        <div class="empty-icon">📚</div>
                        <div class="empty-title">Start searching</div>
                        <div class="empty-description">
                            Type your query above to search through the documentation.
                        </div>
                    `;
                }
                return;
            }
            
            emptyState.style.display = 'none';
            tips.style.display = 'none';
            
            // Results info
            resultsInfo.style.display = 'flex';
            resultsInfo.innerHTML = `
                <span class="results-count">✓ Found ${count} result${count !== 1 ? 's' : ''}</span>
                <span class="results-time">in ${elapsedMs.toFixed(1)}ms</span>
            `;
            
            // Results list
            resultsDiv.innerHTML = results.map((result, index) => {
                // Convert **term** to <mark>term</mark>
                let snippet = result.snippet || result.description || '';
                snippet = snippet.replace(/\*\*([^*]+)\*\*/g, '<mark>$1</mark>');
                
                return `
                    <div class="result ${index === selectedIndex ? 'selected' : ''}" 
                         data-index="${index}"
                         data-url="${escapeHtml(result.url)}">
                        <div class="result-header">
                            <span class="result-number">${index + 1}</span>
                            <a href="${escapeHtml(result.url)}" 
                               class="result-title" 
                               target="_blank"
                               rel="noopener">${escapeHtml(result.title || 'Untitled')}</a>
                            <span class="result-score">${result.score.toFixed(2)}</span>
                        </div>
                        <div class="result-url">${escapeHtml(result.url)}</div>
                        ${snippet ? `<div class="result-snippet">${snippet}</div>` : ''}
                    </div>
                `;
            }).join('');
            
            // Add click handlers
            document.querySelectorAll('.result').forEach(el => {
                el.addEventListener('click', (e) => {
                    if (e.target.tagName !== 'A') {
                        const url = el.dataset.url;
                        window.open(url, '_blank');
                    }
                });
            });
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function updateSelection() {
            document.querySelectorAll('.result').forEach((el, index) => {
                el.classList.toggle('selected', index === selectedIndex);
                if (index === selectedIndex) {
                    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                }
            });
        }
        
        // Input handling with debounce
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                search(searchInput.value);
            }, 150);
        });
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            // Focus search on /
            if (e.key === '/' && document.activeElement !== searchInput) {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
                return;
            }
            
            // Clear on Escape
            if (e.key === 'Escape') {
                searchInput.value = '';
                search('');
                searchInput.blur();
                return;
            }
            
            // Navigation
            if (results.length > 0) {
                if (e.key === 'j' || e.key === 'ArrowDown') {
                    e.preventDefault();
                    selectedIndex = Math.min(selectedIndex + 1, results.length - 1);
                    updateSelection();
                } else if (e.key === 'k' || e.key === 'ArrowUp') {
                    e.preventDefault();
                    selectedIndex = Math.max(selectedIndex - 1, 0);
                    updateSelection();
                } else if ((e.key === 'Enter' || e.key === 'o') && selectedIndex >= 0 && document.activeElement !== searchInput) {
                    e.preventDefault();
                    window.open(results[selectedIndex].url, '_blank');
                } else if (e.key === 'Enter' && document.activeElement === searchInput && selectedIndex >= 0) {
                    e.preventDefault();
                    window.open(results[selectedIndex].url, '_blank');
                }
            }
        });
        
        // Handle Enter in search input
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                if (results.length > 0) {
                    selectedIndex = Math.min(selectedIndex + 1, results.length - 1);
                    updateSelection();
                }
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (results.length > 0) {
                    selectedIndex = Math.max(selectedIndex - 1, 0);
                    updateSelection();
                }
            }
        });
    </script>
</body>
</html>
'''


class SearchHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the search API and web UI."""
    
    engine: SearchEngine = None
    version: str = "1.3.0"
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def send_json(self, data: Dict[str, Any], status: int = 200):
        """Send JSON response."""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)
    
    def send_html(self, html: str, status: int = 200):
        """Send HTML response."""
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        
        if path == '/' or path == '/index.html':
            # Serve the web UI
            html = HTML_TEMPLATE.replace('{{VERSION}}', self.version)
            self.send_html(html)
        
        elif path == '/api/search':
            # Search API
            q = query.get('q', [''])[0]
            limit = int(query.get('limit', ['10'])[0])
            
            if not q:
                self.send_json({'query': '', 'results': [], 'count': 0, 'elapsed_ms': 0})
                return
            
            start_time = time.perf_counter()
            results = self.engine.search(q, top_k=limit)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            self.send_json({
                'query': q,
                'results': results,
                'count': len(results),
                'elapsed_ms': round(elapsed_ms, 2)
            })
        
        elif path == '/api/stats':
            # Stats API
            stats = self.engine.get_stats()
            self.send_json(stats)
        
        else:
            self.send_response(404)
            self.end_headers()


def run_server(engine: SearchEngine, host: str = '127.0.0.1', port: int = 8080, version: str = "1.3.0"):
    """Run the web server."""
    SearchHandler.engine = engine
    SearchHandler.version = version
    
    server = HTTPServer((host, port), SearchHandler)
    
    return server
