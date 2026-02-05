"""
Web server for doc-search with interactive JavaScript UI.

Features instant search, keyboard navigation, and dynamic filtering.
Falls back to pure HTML/CSS with form submissions when --no-javascript is used.
Uses only Python standard library (http.server).
"""

import html
import os
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, List, Dict, Any

from .searcher import SearchEngine, parse_query
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


# ============================================================================
# CSS Styles - Beautiful dark theme, pure CSS
# ============================================================================

CSS = """
/* Dark theme (default) */
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

/* Light theme */
body.light {
    --bg-primary: #ffffff;
    --bg-secondary: #f6f8fa;
    --bg-tertiary: #eaeef2;
    --border: #d0d7de;
    --text-primary: #1f2328;
    --text-secondary: #656d76;
    --text-muted: #8c959f;
    --accent: #0969da;
    --accent-hover: #0550ae;
    --highlight-bg: rgba(9, 105, 218, 0.1);
    --highlight-text: #0550ae;
    --success: #1a7f37;
    --warning: #9a6700;
    --gradient-start: #0969da;
    --gradient-end: #8250df;
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

.search-input-wrapper {
    position: relative;
    flex: 1;
}

.search-input {
    width: 100%;
    padding: 0.875rem 2.5rem 0.875rem 1rem;
    font-size: 1.125rem;
    background: var(--bg-secondary);
    border: 2px solid var(--border);
    border-radius: 10px;
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
    box-sizing: border-box;
}

.search-clear {
    position: absolute;
    right: 0.75rem;
    top: 50%;
    transform: translateY(-50%);
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
    font-size: 1.1rem;
    padding: 0.25rem;
    line-height: 1;
}

.search-clear:hover {
    color: var(--text-primary);
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

/* Search options row */
.search-options {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 1rem;
    margin-top: 0.75rem;
    font-size: 0.875rem;
}

.search-option {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    color: var(--text-secondary);
}

.search-option label {
    cursor: pointer;
}

.search-option select {
    padding: 0.35rem 0.5rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.875rem;
    cursor: pointer;
}

.search-option select:focus {
    outline: none;
    border-color: var(--accent);
}

.search-option input[type="checkbox"] {
    width: 1rem;
    height: 1rem;
    accent-color: var(--accent);
    cursor: pointer;
}

/* Theme toggle */
.theme-toggle {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.25rem;
}

.theme-btn {
    padding: 0.35rem 0.5rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    text-decoration: none;
    font-size: 1rem;
    line-height: 1;
    opacity: 0.5;
    transition: opacity 0.15s;
}

.theme-btn:hover {
    opacity: 0.8;
}

.theme-btn.active {
    opacity: 1;
    border-color: var(--accent);
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
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.75rem;
    color: var(--text-muted);
}

.result-score-bar {
    width: 40px;
    height: 6px;
    background: var(--bg-tertiary);
    border-radius: 3px;
    overflow: hidden;
}

.result-score-fill {
    display: block;
    height: 100%;
    border-radius: 3px;
    transition: width 0.2s ease;
}

.result-score-fill.score-high {
    background: #22c55e;
}

.result-score-fill.score-medium {
    background: #eab308;
}

.result-score-fill.score-low {
    background: #ef4444;
}

.result-score-pct {
    font-size: 0.7rem;
    font-weight: 600;
    min-width: 2.5em;
}

.result-score-pct.score-high {
    color: #22c55e;
}

.result-score-pct.score-medium {
    color: #eab308;
}

.result-score-pct.score-low {
    color: #ef4444;
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

/* HTML5 <mark> element for semantic highlighting */
mark {
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

/* Spell check suggestion */
.spell-suggestion {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.spell-suggestion-icon {
    font-size: 1.25rem;
}

.spell-suggestion-text {
    color: var(--text-secondary);
}

.spell-suggestion-link {
    color: var(--accent);
    font-weight: 600;
    text-decoration: none;
}

.spell-suggestion-link:hover {
    color: var(--accent-hover);
    text-decoration: underline;
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

/* Pagination */
.pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 0.5rem;
    margin-top: 2rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border);
}

.pagination a, .pagination span {
    padding: 0.5rem 1rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
}

.pagination a {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    color: var(--text-primary);
    text-decoration: none;
    transition: border-color 0.2s, background 0.2s;
}

.pagination a:hover {
    border-color: var(--accent);
    background: var(--bg-tertiary);
    text-decoration: none;
}

.pagination .current {
    background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
    color: white;
}

.pagination .disabled {
    color: var(--text-muted);
    cursor: not-allowed;
}

.pagination .page-info {
    color: var(--text-secondary);
    font-size: 0.875rem;
}

/* Facet filters */
.facet-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    padding: 1rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
}

.facet-label {
    color: var(--text-muted);
    font-size: 0.875rem;
    font-weight: 500;
    padding: 0.5rem 0;
    margin-right: 0.5rem;
}

.facet-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.4rem 0.75rem;
    font-size: 0.8125rem;
    font-weight: 500;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-secondary);
    text-decoration: none;
    transition: all 0.2s;
}

.facet-btn:hover {
    border-color: var(--accent);
    color: var(--text-primary);
    text-decoration: none;
}

.facet-btn.active {
    background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
    border-color: transparent;
    color: white;
}

.facet-btn.active:hover {
    opacity: 0.9;
}

.facet-count {
    background: rgba(255, 255, 255, 0.15);
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    font-size: 0.75rem;
}

.facet-btn:not(.active) .facet-count {
    background: var(--bg-primary);
}
"""


def escape(text: str) -> str:
    """HTML escape text."""
    return html.escape(str(text)) if text else ""


def highlight_snippet(snippet: str) -> str:
    """Convert **term** markers to <mark> elements (HTML5 semantic highlighting)."""
    if not snippet:
        return ""
    
    result = escape(snippet)
    # Replace **term** with <mark> elements
    import re
    result = re.sub(
        r'\*\*([^*]+)\*\*',
        r'<mark>\1</mark>',
        result
    )
    return result


def _render_javascript(no_javascript: bool, query: str, per_page: int, theme: str) -> str:
    """Render the JavaScript block for instant search (or empty if disabled)."""
    if no_javascript:
        return ""
    
    return '''
<script>
(function() {
    'use strict';
    
    // State
    let currentRequest = null;
    let searchTimeout = null;
    const DEBOUNCE_MS = 200;
    
    // DOM elements
    const form = document.querySelector('.search-form');
    const input = document.querySelector('.search-input');
    const resultsContainer = document.querySelector('.main');
    const searchButton = document.querySelector('.search-button');
    
    if (!form || !input) return;
    
    // Get current options from form
    function getSearchOptions() {
        const sortSelect = document.querySelector('select[name="sort"]');
        const limitSelect = document.querySelector('select[name="limit"]');
        const exactCheckbox = document.querySelector('input[name="exact"]');
        
        return {
            sort: sortSelect ? sortSelect.value : 'relevance',
            limit: limitSelect ? limitSelect.value : '10',
            exact: exactCheckbox ? (exactCheckbox.checked ? '1' : '') : ''
        };
    }
    
    // Build search URL
    function buildSearchUrl(query, page = 1) {
        const opts = getSearchOptions();
        const params = new URLSearchParams();
        params.set('q', query);
        if (page > 1) params.set('page', page);
        if (opts.sort !== 'relevance') params.set('sort', opts.sort);
        if (opts.limit !== '10') params.set('limit', opts.limit);
        if (opts.exact) params.set('exact', '1');
        
        // Get active facet if any
        const activeFacet = document.querySelector('.facet-btn.active[href*="category="]');
        if (activeFacet) {
            const url = new URL(activeFacet.href);
            const category = url.searchParams.get('category');
            if (category) params.set('category', category);
        }
        
        return params;
    }
    
    // Escape HTML
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Convert **term** to <mark>term</mark>
    function highlightSnippet(text) {
        if (!text) return '';
        return escapeHtml(text).replace(/\\*\\*([^*]+)\\*\\*/g, '<mark>$1</mark>');
    }
    
    // Get score color class
    function getScoreClass(pct) {
        if (pct >= 70) return 'score-high';
        if (pct >= 40) return 'score-medium';
        return 'score-low';
    }
    
    // Render a single result
    function renderResult(r) {
        const scoreClass = getScoreClass(r.score_pct);
        const snippet = r.snippet ? `<div class="result-snippet">${highlightSnippet(r.snippet)}</div>` : '';
        
        return `
            <div class="result">
                <div class="result-header">
                    <span class="result-number">${r.rank}</span>
                    <a href="${escapeHtml(r.url)}" class="result-title" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>
                    <span class="result-score" title="Score: ${r.score.toFixed(2)}">
                        <span class="result-score-bar"><span class="result-score-fill ${scoreClass}" style="width: ${r.score_pct}%"></span></span>
                        <span class="result-score-pct ${scoreClass}">${r.score_pct}%</span>
                    </span>
                </div>
                <div class="result-url">${escapeHtml(r.url)}</div>
                ${snippet}
            </div>
        `;
    }
    
    // Render pagination
    function renderPagination(data) {
        if (data.total_pages <= 1) return '';
        
        const page = data.page;
        const totalPages = data.total_pages;
        const params = buildSearchUrl(data.query, 1);
        
        let html = '<div class="pagination">';
        
        // First/Prev
        if (page > 1) {
            params.set('page', '1');
            html += `<a href="#" data-page="1">« First</a>`;
            html += `<a href="#" data-page="${page - 1}">← Prev</a>`;
        } else {
            html += '<span class="disabled">« First</span>';
            html += '<span class="disabled">← Prev</span>';
        }
        
        // Page numbers
        const startPage = Math.max(1, page - 3);
        const endPage = Math.min(totalPages, page + 3);
        
        if (startPage > 1) {
            html += `<a href="#" data-page="1">1</a>`;
            if (startPage > 2) html += '<span class="page-info">...</span>';
        }
        
        for (let p = startPage; p <= endPage; p++) {
            if (p === page) {
                html += `<span class="current">${p}</span>`;
            } else {
                html += `<a href="#" data-page="${p}">${p}</a>`;
            }
        }
        
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) html += '<span class="page-info">...</span>';
            html += `<a href="#" data-page="${totalPages}">${totalPages}</a>`;
        }
        
        // Next/Last
        if (page < totalPages) {
            html += `<a href="#" data-page="${page + 1}">Next →</a>`;
            html += `<a href="#" data-page="${totalPages}">Last »</a>`;
        } else {
            html += '<span class="disabled">Next →</span>';
            html += '<span class="disabled">Last »</span>';
        }
        
        html += '</div>';
        return html;
    }
    
    // Render results
    function renderResults(data) {
        const formHtml = form.outerHTML;
        const datalist = document.getElementById('search-suggestions');
        const datalistHtml = datalist ? datalist.outerHTML : '';
        
        if (!data.results || data.results.length === 0) {
            // No results
            let suggestionHtml = '';
            if (data.suggestion) {
                suggestionHtml = `
                    <div class="spell-suggestion">
                        <span class="spell-suggestion-icon">💡</span>
                        <span class="spell-suggestion-text">Did you mean:</span>
                        <a href="#" class="spell-suggestion-link" data-suggestion="${escapeHtml(data.suggestion)}">${escapeHtml(data.suggestion)}</a>?
                    </div>
                `;
            }
            
            resultsContainer.innerHTML = `
                ${formHtml}
                ${datalistHtml}
                ${suggestionHtml}
                <div class="no-results">
                    <div class="no-results-icon">🔍</div>
                    <div>No results found. Try different keywords.</div>
                </div>
            `;
        } else {
            // Has results
            const startNum = (data.page - 1) * data.per_page + 1;
            const endNum = Math.min(data.page * data.per_page, data.total);
            
            const resultsHtml = data.results.map(renderResult).join('');
            const paginationHtml = renderPagination(data);
            
            resultsContainer.innerHTML = `
                ${formHtml}
                ${datalistHtml}
                <div class="results-info">
                    <span class="results-count">✓ Found ${data.total} result${data.total !== 1 ? 's' : ''}</span>
                    <span class="results-time">in ${data.elapsed_ms.toFixed(1)}ms</span>
                    <span class="results-query">showing ${startNum}-${endNum} for "${escapeHtml(data.query)}"</span>
                </div>
                <div class="results">
                    ${resultsHtml}
                </div>
                ${paginationHtml}
            `;
        }
        
        // Re-bind event listeners after DOM update
        bindEventListeners();
    }
    
    // Show loading state
    function showLoading() {
        searchButton.textContent = '...';
        searchButton.disabled = true;
    }
    
    // Hide loading state
    function hideLoading() {
        searchButton.textContent = 'Search';
        searchButton.disabled = false;
    }
    
    // Perform search
    function doSearch(query, page = 1) {
        if (!query.trim()) {
            // Reload page to show welcome state
            window.location.href = '/';
            return;
        }
        
        // Cancel pending request
        if (currentRequest) {
            currentRequest.abort();
        }
        
        showLoading();
        
        // Build API URL
        const params = buildSearchUrl(query, page);
        const apiUrl = '/api/search?' + params.toString();
        
        // Update browser URL
        const browserUrl = '/?' + params.toString();
        window.history.pushState({ query, page }, '', browserUrl);
        
        // Create abort controller
        const controller = new AbortController();
        currentRequest = controller;
        
        fetch(apiUrl, { signal: controller.signal })
            .then(response => {
                if (!response.ok) throw new Error('Search failed');
                return response.json();
            })
            .then(data => {
                hideLoading();
                renderResults(data);
            })
            .catch(err => {
                hideLoading();
                if (err.name !== 'AbortError') {
                    console.error('Search error:', err);
                }
            })
            .finally(() => {
                currentRequest = null;
            });
    }
    
    // Debounced search for typing
    function debouncedSearch() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            doSearch(input.value, 1);
        }, DEBOUNCE_MS);
    }
    
    // Bind event listeners
    function bindEventListeners() {
        const newForm = document.querySelector('.search-form');
        const newInput = document.querySelector('.search-input');
        
        if (newForm) {
            newForm.addEventListener('submit', (e) => {
                e.preventDefault();
                clearTimeout(searchTimeout);
                doSearch(newInput.value, 1);
            });
        }
        
        if (newInput) {
            newInput.addEventListener('input', debouncedSearch);
        }
        
        // Pagination links
        document.querySelectorAll('.pagination a[data-page]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(link.dataset.page);
                doSearch(newInput.value, page);
            });
        });
        
        // Spelling suggestion links
        document.querySelectorAll('.spell-suggestion-link[data-suggestion]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const suggestion = link.dataset.suggestion;
                newInput.value = suggestion;
                doSearch(suggestion, 1);
            });
        });
        
        // Clear button
        const clearBtn = document.querySelector('.search-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                newInput.value = '';
                newInput.focus();
            });
        }
    }
    
    // Handle back/forward navigation
    window.addEventListener('popstate', (e) => {
        if (e.state && e.state.query) {
            input.value = e.state.query;
            doSearch(e.state.query, e.state.page || 1);
        } else {
            // Go back to home
            window.location.reload();
        }
    });
    
    // Initial binding
    bindEventListeners();
})();
</script>'''


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
    unique_terms = stats.get('unique_terms', 0)
    
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
                url = escape(r['url'])
                snippet = highlight_snippet(r.get('snippet', '') or r.get('description', ''))
                score = r.get('score', 0)
                
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
                    <span class="result-score-pct {score_color}">{score_pct}%</span>
                </span>''' if show_scores else ''
                
                snippet_html = f'<div class="result-snippet">{snippet}</div>' if snippet else ""
                
                results_html += f'''
                <div class="result">
                    <div class="result-header">
                        <span class="result-number">{i}</span>
                        <a href="{url}" class="result-title" target="_blank" rel="noopener">{title}</a>
                        {score_html}
                    </div>
                    <div class="result-url">{url}</div>
                    {snippet_html}
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
    dark_url = "/?" + (base_params + "&theme=dark" if base_params else "theme=dark")
    light_url = "/?" + (base_params + "&theme=light" if base_params else "theme=light")
    dark_class = "theme-btn active" if theme == "dark" else "theme-btn"
    light_class = "theme-btn active" if theme == "light" else "theme-btn"
    
    search_options_html = f'''
            <div class="search-options">
                <div class="search-option">
                    <label for="sort">Sort:</label>
                    <select name="sort" id="sort">
                        <option value="relevance" {sort_relevance_sel}>Relevance</option>
                        <option value="date" {sort_date_sel}>Newest</option>
                    </select>
                </div>
                <div class="search-option">
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
                    <a href="{dark_url}" class="{dark_class}" title="Dark theme">{_e('moon')}</a>
                    <a href="{light_url}" class="{light_class}" title="Light theme">{_e('sun')}</a>
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
                    <button type="button" class="search-clear" onclick="this.previousElementSibling.value='';this.previousElementSibling.focus();" aria-label="Clear search">✕</button>
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
{_render_javascript(no_javascript, query, per_page, theme)}
</body>
</html>'''


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
    enable_synonyms: bool = True  # Enable synonym expansion toggle
    no_javascript: bool = False  # Serve pure HTML/CSS UI without JavaScript
    
    def log_message(self, format, *args):
        """Log HTTP requests if enabled."""
        if self.log_requests:
            message = format % args
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] {self.address_string()} - {message}")
    
    def send_html(self, content: str, status: int = 200):
        """Send HTML response."""
        body = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def send_json(self, data: dict, status: int = 200):
        """Send JSON response."""
        import json
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        
        # Handle /health endpoint
        if parsed.path == '/health':
            self.handle_health()
            return
        
        # Handle /suggest endpoint for autocomplete
        if parsed.path == '/suggest':
            self.handle_suggest(parsed.query)
            return
        
        # Handle /api/search endpoint for JSON results (instant search)
        if parsed.path == '/api/search':
            self.handle_api_search(parsed.query)
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
                import inspect
                sig = inspect.signature(self.engine.search)
                if 'expand_synonyms' in sig.parameters:
                    all_results = self.engine.search(search_query, top_k=max_results, expand_synonyms=True)
                else:
                    all_results = self.engine.search(search_query, top_k=max_results)
            else:
                all_results = self.engine.search(search_query, top_k=max_results)
            elapsed_ms = (time.perf_counter() - search_start) * 1000
            
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
            
            # Slice for current page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_results = filtered_results[start_idx:end_idx]
            
            # If page is beyond results, redirect to page 1
            if not page_results and total_results > 0:
                page = 1
                page_results = filtered_results[:per_page]
            
            # Check for spelling suggestions when results are low
            suggestion = None
            if total_results == 0 and hasattr(self.engine, 'get_spelling_suggestion'):
                suggestion = self.engine.get_spelling_suggestion(query)
                # Only show suggestion if it's different from the query
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
            suggestions = self.engine.get_autocomplete_suggestions(prefix, limit)
            self.send_json({'suggestions': suggestions})
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
    def handle_api_search(self, query_string: str):
        """Handle /api/search endpoint for instant search.
        
        Returns JSON with search results for JavaScript-driven UI.
        Query params:
            q: search query
            page: page number (default 1)
            limit: results per page (10, 25, or 50)
            category: facet filter
            exact: 1 for exact match
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
                'page': 1,
                'per_page': self.per_page,
                'elapsed_ms': 0,
                'suggestion': None,
                'facets': None
            })
            return
        
        # Get page number (default 1, minimum 1)
        try:
            page = max(1, int(query_params.get('page', ['1'])[0]))
        except ValueError:
            page = 1
        
        # Get facet filter (category)
        category_filter = query_params.get('category', [''])[0].strip() if self.enable_facets else ''
        
        # Get results limit (per page)
        try:
            per_page = int(query_params.get('limit', [str(self.per_page)])[0])
            if per_page not in (10, 25, 50):
                per_page = self.per_page
        except ValueError:
            per_page = self.per_page
        
        # Get exact match toggle
        exact_match = query_params.get('exact', [''])[0] == '1'
        
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
            
            # Get facet counts before filtering
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
            
            # Slice for current page
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_results = filtered_results[start_idx:end_idx]
            
            # Check for spelling suggestions when results are low
            suggestion = None
            if total_results == 0 and hasattr(self.engine, 'get_spelling_suggestion'):
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
                
                json_results.append({
                    'rank': i,
                    'title': r.get('title', 'Untitled') or 'Untitled',
                    'url': r['url'],
                    'snippet': r.get('snippet', '') or r.get('description', ''),
                    'score': round(score, 4),
                    'score_pct': score_pct,
                    'facets': r.get('facets', {})
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
                'global_max_score': round(global_max_score, 4)
            }
            
            self.send_json(response)
            
        except Exception as e:
            self.send_json({'error': str(e)}, 500)
    
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
                'terms': stats.get('unique_terms', 0),
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
    enable_synonyms: bool = True,
    no_javascript: bool = False
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
        enable_synonyms: If True, show synonym expansion toggle (default: True)
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
    server = HTTPServer((host, port), SearchHandler)
    return server
