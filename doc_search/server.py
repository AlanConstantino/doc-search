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
# CSS Styles - Beautiful dark theme with light mode support
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

/* Search history dropdown */
.search-history-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-top: none;
    border-radius: 0 0 10px 10px;
    max-height: 300px;
    overflow-y: auto;
    z-index: 100;
    display: none;
}

.search-history-dropdown.visible {
    display: block;
}

.history-header {
    padding: 0.5rem 1rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
}

.history-clear-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.75rem;
    padding: 0.25rem;
}

.history-clear-btn:hover {
    color: var(--accent);
}

.history-item {
    padding: 0.5rem 1rem;
    cursor: pointer;
    transition: background 0.1s;
}

.history-item:hover {
    background: var(--bg-tertiary);
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

/* Theme toggle - iOS style switch */
.theme-toggle {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.theme-toggle-label {
    font-size: 1rem;
    opacity: 0.6;
}

.theme-switch {
    position: relative;
    width: 50px;
    height: 26px;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 13px;
    cursor: pointer;
    transition: background 0.3s, border-color 0.3s;
}

.theme-switch:hover {
    border-color: var(--accent);
}

.theme-switch-knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    background: var(--text-primary);
    border-radius: 50%;
    transition: transform 0.3s;
}

.theme-switch.light .theme-switch-knob {
    transform: translateX(24px);
}

.theme-switch.light {
    background: var(--accent);
    border-color: var(--accent);
}

/* Search within results highlight input - fixed overlay at top */
.search-highlight-bar {
    display: none;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-bottom: 2px solid var(--accent);
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
}

.search-highlight-bar.visible {
    display: flex;
}

.search-highlight-input {
    flex: 1;
    padding: 0.5rem;
    background: var(--bg-tertiary);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 0.875rem;
}

.search-highlight-input:focus {
    outline: none;
    border-color: var(--accent);
}

.search-highlight-count {
    font-size: 0.75rem;
    color: var(--text-muted);
    min-width: 60px;
}

.search-highlight-close {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
    font-size: 1rem;
    padding: 0.25rem;
}

.search-highlight-close:hover {
    color: var(--text-primary);
}

/* Cmd+F highlight style */
.cmd-f-highlight {
    background: #ffff00;
    color: #000;
    padding: 0.1em 0.15em;
    border-radius: 2px;
}

.cmd-f-highlight.current {
    background: #ff9632;
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

/* Loading indicator */
.loading-indicator {
    display: none;
    text-align: center;
    padding: 2rem;
    color: var(--text-muted);
}

.loading-indicator.visible {
    display: block;
}

.loading-spinner {
    display: inline-block;
    width: 24px;
    height: 24px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
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
    transition: border-color 0.2s, background 0.2s, outline 0.1s;
}

.result:hover {
    border-color: var(--accent);
    background: var(--bg-tertiary);
}

.result.selected {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
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

.doc-type-badge {
    display: inline-block;
    padding: 0.15rem 0.4rem;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    border-radius: 3px;
    margin-left: 0.5rem;
    vertical-align: middle;
}

.doc-type-badge.pdf {
    background: #dc2626;
    color: white;
}

.doc-type-badge.html {
    background: var(--bg-tertiary);
    color: var(--text-muted);
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

/* Copy link button */
.copy-link-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.875rem;
    padding: 0.25rem;
    margin-top: 0.5rem;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    transition: color 0.15s;
}

.copy-link-btn:hover {
    color: var(--accent);
}

.copy-link-btn.copied {
    color: #22c55e;
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
    cursor: pointer;
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
    cursor: pointer;
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

/* Infinite scroll sentinel */
.scroll-sentinel {
    height: 1px;
    margin-top: 1rem;
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
    cursor: pointer;
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

/* Clear filters link */
.facet-clear {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-left: 0.5rem;
    cursor: pointer;
}

.facet-clear:hover {
    color: var(--accent);
}

.facet-separator {
    color: var(--border);
    margin: 0 0.5rem;
}
"""


# ============================================================================
# JavaScript for instant search, history, keyboard nav, infinite scroll, etc.
# ============================================================================

JAVASCRIPT = """
(function() {
    'use strict';
    
    // ========================================================================
    // State
    // ========================================================================
    let currentRequest = null;
    let searchTimeout = null;
    const DEBOUNCE_MS = 200;
    const HISTORY_KEY = 'doc-search-history';
    const THEME_KEY = 'doc-search-theme';
    const MAX_HISTORY = 10;
    
    let selectedResultIndex = -1;
    let currentPage = 1;
    let totalPages = 1;
    let isLoadingMore = false;
    let allLoadedResults = [];
    let currentQuery = '';
    let currentFacet = null;
    let currentType = null;
    
    // Cmd+F highlighting state
    let highlightMatches = [];
    let currentHighlightIndex = -1;
    
    // ========================================================================
    // DOM Elements
    // ========================================================================
    const form = document.querySelector('.search-form');
    const input = document.querySelector('.search-input');
    const searchButton = document.querySelector('.search-button');
    const resultsContainer = document.querySelector('.results');
    const mainContainer = document.querySelector('.main');
    
    if (!form || !input) return;
    
    // Hide Results dropdown when JS is enabled (infinite scroll makes it redundant)
    const limitOption = document.querySelector('.limit-option');
    if (limitOption) limitOption.style.display = 'none';
    
    // ========================================================================
    // Theme Management (#180)
    // ========================================================================
    function getStoredTheme() {
        try {
            return localStorage.getItem(THEME_KEY);
        } catch (e) {
            return null;
        }
    }
    
    function setStoredTheme(theme) {
        try {
            localStorage.setItem(THEME_KEY, theme);
        } catch (e) {}
    }
    
    function applyTheme(theme) {
        document.body.classList.toggle('light', theme === 'light');
        // Update theme buttons
        document.querySelectorAll('.theme-btn').forEach(btn => {
            const isLight = btn.getAttribute('data-theme') === 'light';
            const isDark = btn.getAttribute('data-theme') === 'dark';
            if ((theme === 'light' && isLight) || (theme !== 'light' && isDark)) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }
    
    function initTheme() {
        // Check localStorage first
        let theme = getStoredTheme();
        
        // Fall back to prefers-color-scheme
        if (!theme) {
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
                theme = 'light';
            } else {
                theme = 'dark';
            }
        }
        
        applyTheme(theme);
        
        // Listen for system theme changes
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
                if (!getStoredTheme()) {
                    applyTheme(e.matches ? 'light' : 'dark');
                }
            });
        }
    }
    
    function setupThemeToggle() {
        const toggle = document.querySelector('.theme-switch');
        if (!toggle) return;
        
        // Remove href for JS mode
        toggle.removeAttribute('href');
        
        toggle.addEventListener('click', (e) => {
            e.preventDefault();
            const isLight = toggle.classList.contains('light');
            const newTheme = isLight ? 'dark' : 'light';
            setStoredTheme(newTheme);
            applyTheme(newTheme);
            toggle.classList.toggle('light', newTheme === 'light');
        });
    }
    
    // ========================================================================
    // Search History (#174)
    // ========================================================================
    function getSearchHistory() {
        try {
            const stored = localStorage.getItem(HISTORY_KEY);
            return stored ? JSON.parse(stored) : [];
        } catch (e) {
            return [];
        }
    }
    
    function saveSearchHistory(history) {
        try {
            localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
        } catch (e) {}
    }
    
    function addToHistory(query) {
        if (!query || !query.trim()) return;
        query = query.trim();
        
        let history = getSearchHistory();
        history = history.filter(q => q.toLowerCase() !== query.toLowerCase());
        history.unshift(query);
        if (history.length > MAX_HISTORY) {
            history = history.slice(0, MAX_HISTORY);
        }
        saveSearchHistory(history);
    }
    
    function clearHistory() {
        saveSearchHistory([]);
        hideHistoryDropdown();
    }
    
    let historyDropdown = null;
    
    function createHistoryDropdown() {
        if (historyDropdown) return historyDropdown;
        
        const dropdown = document.createElement('div');
        dropdown.className = 'search-history-dropdown';
        
        const wrapper = document.querySelector('.search-input-wrapper');
        if (wrapper) {
            wrapper.appendChild(dropdown);
        }
        
        historyDropdown = dropdown;
        return dropdown;
    }
    
    function showHistoryDropdown() {
        const history = getSearchHistory();
        if (history.length === 0) return;
        
        const dropdown = createHistoryDropdown();
        
        let html = '<div class="history-header">';
        html += '<span>Recent searches</span>';
        html += '<button type="button" class="history-clear-btn">Clear</button>';
        html += '</div>';
        
        history.forEach((q) => {
            html += '<div class="history-item" data-query="' + escapeHtml(q) + '">' + escapeHtml(q) + '</div>';
        });
        
        dropdown.innerHTML = html;
        dropdown.classList.add('visible');
        
        dropdown.querySelectorAll('.history-item').forEach(item => {
            item.addEventListener('click', () => {
                input.value = item.dataset.query;
                hideHistoryDropdown();
                doSearch(item.dataset.query, 1);
            });
        });
        
        const clearBtn = dropdown.querySelector('.history-clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                clearHistory();
            });
        }
    }
    
    function hideHistoryDropdown() {
        if (historyDropdown) {
            historyDropdown.classList.remove('visible');
        }
    }
    
    // ========================================================================
    // Keyboard Navigation (#175)
    // ========================================================================
    function getResultElements() {
        return document.querySelectorAll('.result');
    }
    
    function highlightResult(index) {
        const results = getResultElements();
        results.forEach(r => r.classList.remove('selected'));
        
        if (index >= 0 && index < results.length) {
            selectedResultIndex = index;
            const result = results[index];
            result.classList.add('selected');
            result.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
            selectedResultIndex = -1;
        }
    }
    
    function openSelectedResult(newTab = false) {
        const results = getResultElements();
        if (selectedResultIndex >= 0 && selectedResultIndex < results.length) {
            const link = results[selectedResultIndex].querySelector('.result-title');
            if (link) {
                if (newTab) {
                    window.open(link.href, '_blank');
                } else {
                    window.location.href = link.href;
                }
            }
        }
    }
    
    function handleKeyboardNavigation(e) {
        const results = getResultElements();
        
        // Cmd+F / Ctrl+F for search within results
        if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
            if (results.length > 0) {
                e.preventDefault();
                showHighlightBar();
                return;
            }
        }
        
        // Escape to clear
        if (e.key === 'Escape') {
            e.preventDefault();
            highlightResult(-1);
            hideHistoryDropdown();
            hideHighlightBar();
            input.focus();
            return;
        }
        
        if (results.length === 0) return;
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (selectedResultIndex < results.length - 1) {
                    highlightResult(selectedResultIndex + 1);
                }
                break;
            case 'ArrowUp':
                e.preventDefault();
                if (selectedResultIndex > 0) {
                    highlightResult(selectedResultIndex - 1);
                } else if (selectedResultIndex === 0) {
                    highlightResult(-1);
                    input.focus();
                }
                break;
            case 'Enter':
                if (selectedResultIndex >= 0 && document.activeElement !== input) {
                    e.preventDefault();
                    openSelectedResult(e.ctrlKey || e.metaKey);
                }
                break;
        }
    }
    
    // ========================================================================
    // Search Within Results - Cmd+F Highlighting (#179)
    // ========================================================================
    let highlightBar = null;
    
    function createHighlightBar() {
        if (highlightBar) return highlightBar;
        
        const bar = document.createElement('div');
        bar.className = 'search-highlight-bar';
        bar.innerHTML = `
            <input type="text" class="search-highlight-input" placeholder="Search within results...">
            <span class="search-highlight-count"></span>
            <button type="button" class="search-highlight-close">✕</button>
        `;
        
        // Append to body for fixed positioning overlay
        document.body.appendChild(bar);
        
        const highlightInput = bar.querySelector('.search-highlight-input');
        const closeBtn = bar.querySelector('.search-highlight-close');
        
        let highlightTimeout = null;
        highlightInput.addEventListener('input', () => {
            clearTimeout(highlightTimeout);
            highlightTimeout = setTimeout(() => {
                highlightInResults(highlightInput.value);
            }, 100);
        });
        
        highlightInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (e.shiftKey) {
                    navigateHighlight(-1);
                } else {
                    navigateHighlight(1);
                }
            } else if (e.key === 'Escape') {
                hideHighlightBar();
            }
        });
        
        closeBtn.addEventListener('click', hideHighlightBar);
        
        highlightBar = bar;
        return bar;
    }
    
    function showHighlightBar() {
        const bar = createHighlightBar();
        bar.classList.add('visible');
        const highlightInput = bar.querySelector('.search-highlight-input');
        highlightInput.focus();
        highlightInput.select();
    }
    
    function hideHighlightBar() {
        if (highlightBar) {
            highlightBar.classList.remove('visible');
            clearHighlights();
        }
    }
    
    function highlightInResults(text) {
        clearHighlights();
        if (!text || text.length < 2) {
            updateHighlightCount(0, 0);
            return;
        }
        
        const snippets = document.querySelectorAll('.result-snippet');
        let totalMatches = 0;
        
        snippets.forEach(snippet => {
            const html = snippet.innerHTML;
            const regex = new RegExp('(' + escapeRegex(text) + ')', 'gi');
            let matchCount = 0;
            
            const newHtml = html.replace(regex, (match) => {
                matchCount++;
                totalMatches++;
                return '<span class="cmd-f-highlight" data-match-index="' + (totalMatches - 1) + '">' + match + '</span>';
            });
            
            if (matchCount > 0) {
                snippet.innerHTML = newHtml;
            }
        });
        
        highlightMatches = document.querySelectorAll('.cmd-f-highlight');
        currentHighlightIndex = -1;
        updateHighlightCount(0, totalMatches);
        
        if (totalMatches > 0) {
            navigateHighlight(1);
        }
    }
    
    function clearHighlights() {
        document.querySelectorAll('.cmd-f-highlight').forEach(el => {
            const text = el.textContent;
            el.replaceWith(document.createTextNode(text));
        });
        highlightMatches = [];
        currentHighlightIndex = -1;
    }
    
    function navigateHighlight(direction) {
        if (highlightMatches.length === 0) return;
        
        if (currentHighlightIndex >= 0) {
            highlightMatches[currentHighlightIndex].classList.remove('current');
        }
        
        currentHighlightIndex += direction;
        if (currentHighlightIndex >= highlightMatches.length) {
            currentHighlightIndex = 0;
        } else if (currentHighlightIndex < 0) {
            currentHighlightIndex = highlightMatches.length - 1;
        }
        
        const current = highlightMatches[currentHighlightIndex];
        current.classList.add('current');
        current.scrollIntoView({ behavior: 'smooth', block: 'center' });
        
        updateHighlightCount(currentHighlightIndex + 1, highlightMatches.length);
    }
    
    function updateHighlightCount(current, total) {
        const countEl = highlightBar?.querySelector('.search-highlight-count');
        if (countEl) {
            countEl.textContent = total > 0 ? current + ' of ' + total : '';
        }
    }
    
    function escapeRegex(string) {
        return string.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
    }
    
    // ========================================================================
    // Result Previews (#177)
    // ========================================================================
    // Copy Link Button
    // ========================================================================
    function setupCopyLinkButtons() {
        document.querySelectorAll('.result').forEach(result => {
            // Add copy link button if not exists
            if (!result.querySelector('.copy-link-btn')) {
                const url = result.querySelector('.result-title')?.href;
                if (url) {
                    const btn = document.createElement('button');
                    btn.className = 'copy-link-btn';
                    btn.innerHTML = 'Copy link';
                    btn.addEventListener('click', () => copyLink(btn, url));
                    
                    // Add after snippet or at end of result
                    const snippet = result.querySelector('.result-snippet');
                    if (snippet) {
                        snippet.parentNode.insertBefore(btn, snippet.nextSibling);
                    } else {
                        result.appendChild(btn);
                    }
                }
            }
        });
    }
    
    function copyLink(btn, url) {
        navigator.clipboard.writeText(url).then(() => {
            btn.innerHTML = '✓ Copied!';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = 'Copy link';
                btn.classList.remove('copied');
            }, 2000);
        }).catch(() => {
            // Fallback for older browsers
            const input = document.createElement('input');
            input.value = url;
            document.body.appendChild(input);
            input.select();
            document.execCommand('copy');
            document.body.removeChild(input);
            btn.innerHTML = '✓ Copied!';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = 'Copy link';
                btn.classList.remove('copied');
            }, 2000);
        });
    }
    
    // ========================================================================
    // Infinite Scroll (#176)
    // ========================================================================
    let scrollObserver = null;
    let scrollSentinel = null;
    
    function setupInfiniteScroll() {
        if (!('IntersectionObserver' in window)) return;
        
        scrollObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !isLoadingMore && currentPage < totalPages) {
                    loadMoreResults();
                }
            });
        }, { rootMargin: '100px' });
    }
    
    function createScrollSentinel() {
        if (scrollSentinel) {
            scrollSentinel.remove();
        }
        
        scrollSentinel = document.createElement('div');
        scrollSentinel.className = 'scroll-sentinel';
        
        const results = document.querySelector('.results');
        if (results) {
            results.parentNode.insertBefore(scrollSentinel, results.nextSibling);
        }
        
        if (scrollObserver && currentPage < totalPages) {
            scrollObserver.observe(scrollSentinel);
        }
    }
    
    function removeScrollSentinel() {
        if (scrollSentinel) {
            if (scrollObserver) {
                scrollObserver.unobserve(scrollSentinel);
            }
            scrollSentinel.remove();
            scrollSentinel = null;
        }
    }
    
    function loadMoreResults() {
        if (isLoadingMore || currentPage >= totalPages) return;
        
        isLoadingMore = true;
        showLoadingIndicator();
        
        const nextPage = currentPage + 1;
        const params = buildSearchParams(currentQuery, nextPage);
        
        fetch('/api/search?' + params.toString(), { signal: currentRequest?.signal })
            .then(response => response.json())
            .then(data => {
                hideLoadingIndicator();
                isLoadingMore = false;
                currentPage = data.page;
                totalPages = data.total_pages;
                
                appendResults(data.results);
                allLoadedResults = allLoadedResults.concat(data.results);
                
                // Update "showing X-Y" text to reflect all loaded results
                updateResultsInfo(allLoadedResults.length, data.total);
                
                if (currentPage < totalPages) {
                    createScrollSentinel();
                } else {
                    removeScrollSentinel();
                }
            })
            .catch(err => {
                hideLoadingIndicator();
                isLoadingMore = false;
                if (err.name !== 'AbortError') {
                    console.error('Load more error:', err);
                }
            });
    }
    
    function showLoadingIndicator() {
        let indicator = document.querySelector('.loading-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.className = 'loading-indicator';
            indicator.innerHTML = '<div class="loading-spinner"></div> Loading more results...';
            const results = document.querySelector('.results');
            if (results) {
                results.parentNode.insertBefore(indicator, results.nextSibling);
            }
        }
        indicator.classList.add('visible');
    }
    
    function hideLoadingIndicator() {
        const indicator = document.querySelector('.loading-indicator');
        if (indicator) {
            indicator.classList.remove('visible');
        }
    }
    
    // ========================================================================
    // Faceted Filtering (#178)
    // ========================================================================
    function setupFacetButtons() {
        document.querySelectorAll('.facet-btn').forEach(btn => {
            // Remove old listeners to avoid duplicates
            const newBtn = btn.cloneNode(true);
            btn.parentNode.replaceChild(newBtn, btn);
            
            newBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                // Guard: don't search if no query
                if (!currentQuery || !currentQuery.trim()) {
                    console.warn('No search query to filter');
                    return;
                }
                
                // Check if it's a type or category filter
                const typeValue = newBtn.dataset.type;
                const categoryValue = newBtn.dataset.category;
                
                if (typeValue !== undefined) {
                    // Type filter clicked
                    currentType = typeValue || null;
                    // Update active state for type buttons only
                    document.querySelectorAll('.facet-btn[data-type]').forEach(b => b.classList.remove('active'));
                    newBtn.classList.add('active');
                } else if (categoryValue !== undefined) {
                    // Category filter clicked
                    currentFacet = categoryValue || null;
                    // Update active state for category buttons only
                    document.querySelectorAll('.facet-btn[data-category]').forEach(b => b.classList.remove('active'));
                    newBtn.classList.add('active');
                }
                
                currentPage = 1;
                allLoadedResults = [];
                doSearch(currentQuery, 1);
            });
        });
    }
    
    // ========================================================================
    // Search API (#172, #173)
    // ========================================================================
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    function highlightSnippet(text) {
        if (!text) return '';
        return escapeHtml(text).replace(/\\*\\*([^*]+)\\*\\*/g, '<mark>$1</mark>');
    }
    
    function getScoreClass(pct) {
        if (pct >= 70) return 'score-high';
        if (pct >= 40) return 'score-medium';
        return 'score-low';
    }
    
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
    
    function buildSearchParams(query, page = 1) {
        const opts = getSearchOptions();
        const params = new URLSearchParams();
        params.set('q', query);
        if (page > 1) params.set('page', page);
        if (opts.sort !== 'relevance') params.set('sort', opts.sort);
        if (opts.limit !== '10') params.set('limit', opts.limit);
        if (opts.exact) params.set('exact', '1');
        if (currentFacet) params.set('category', currentFacet);
        if (currentType) params.set('type', currentType);
        return params;
    }
    
    function renderResult(r) {
        const scoreClass = getScoreClass(r.score_pct);
        const snippet = r.snippet ? '<div class="result-snippet">' + highlightSnippet(r.snippet) + '</div>' : '';
        const docType = r.doc_type || 'html';
        const docTypeBadge = `<span class="doc-type-badge ${docType}">${docType}</span>`;
        
        return `
            <div class="result" data-url="${escapeHtml(r.url)}">
                <div class="result-header">
                    <span class="result-number">${r.rank}</span>
                    <a href="${escapeHtml(r.url)}" class="result-title" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>
                    ${docTypeBadge}
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
    
    function renderFacets(facets, activeFacet, activeType, totalUnfiltered) {
        const hasCategory = facets && facets.category && Object.keys(facets.category).length > 1;
        const hasType = facets && facets.type && Object.keys(facets.type).length > 1;
        
        if (!hasCategory && !hasType) {
            return '';
        }
        
        let html = '<div class="facet-filters">';
        
        // File type filter (PDF/HTML)
        if (hasType) {
            html += '<span class="facet-label">Type:</span>';
            const allTypeClass = !activeType ? 'facet-btn active' : 'facet-btn';
            html += '<button class="' + allTypeClass + '" data-type="">All <span class="facet-count">' + totalUnfiltered + '</span></button>';
            
            const typeSorted = Object.entries(facets.type).sort((a, b) => b[1] - a[1]);
            for (const [type, count] of typeSorted) {
                const isActive = activeType === type;
                const btnClass = isActive ? 'facet-btn active' : 'facet-btn';
                html += '<button class="' + btnClass + '" data-type="' + escapeHtml(type) + '">' + escapeHtml(type.toUpperCase()) + ' <span class="facet-count">' + count + '</span></button>';
            }
            
            if (hasCategory) {
                html += '<span class="facet-separator">|</span>';
            }
        }
        
        // Category filter (URL path based)
        if (hasCategory) {
            html += '<span class="facet-label">Category:</span>';
            const allClass = !activeFacet ? 'facet-btn active' : 'facet-btn';
            html += '<button class="' + allClass + '" data-category="">All</button>';
            
            const sorted = Object.entries(facets.category).sort((a, b) => b[1] - a[1]);
            for (const [category, count] of sorted) {
                const isActive = activeFacet === category;
                const btnClass = isActive ? 'facet-btn active' : 'facet-btn';
                html += '<button class="' + btnClass + '" data-category="' + escapeHtml(category) + '">' + escapeHtml(category) + ' <span class="facet-count">' + count + '</span></button>';
            }
        }
        
        if (activeFacet || activeType) {
            html += '<span class="facet-clear" onclick="window.docSearch.clearFacets()">Clear filters</span>';
        }
        
        html += '</div>';
        return html;
    }
    
    function appendResults(results) {
        const container = document.querySelector('.results');
        if (!container) return;
        
        results.forEach(r => {
            container.insertAdjacentHTML('beforeend', renderResult(r));
        });
        
        setupCopyLinkButtons();
    }
    
    function updateResultsInfo(loaded, total) {
        const resultsQuery = document.querySelector('.results-query');
        if (resultsQuery) {
            resultsQuery.textContent = `showing 1-${loaded} of ${total} for "${currentQuery}"`;
        }
    }
    
    function renderResults(data) {
        selectedResultIndex = -1;
        hideHighlightBar();
        
        // Find or create results container
        let container = document.querySelector('.results');
        const facetsContainer = document.querySelector('.facet-filters');
        const resultsInfo = document.querySelector('.results-info');
        const pagination = document.querySelector('.pagination');
        const noResults = document.querySelector('.no-results');
        const welcome = document.querySelector('.welcome');
        const tips = document.querySelector('.tips');
        const spellSuggestion = document.querySelector('.spell-suggestion');
        
        // Remove old elements
        if (facetsContainer) facetsContainer.remove();
        if (pagination) pagination.remove();
        if (noResults) noResults.remove();
        if (welcome) welcome.remove();
        if (tips) tips.remove();
        if (spellSuggestion) spellSuggestion.remove();
        removeScrollSentinel();
        
        if (!data.results || data.results.length === 0) {
            // No results
            if (resultsInfo) resultsInfo.remove();
            if (container) container.innerHTML = '';
            
            let html = '';
            if (data.suggestion) {
                html += '<div class="spell-suggestion">';
                html += '<span class="spell-suggestion-icon">💡</span>';
                html += '<span class="spell-suggestion-text">Did you mean:</span>';
                html += '<span class="spell-suggestion-link" data-suggestion="' + escapeHtml(data.suggestion) + '">' + escapeHtml(data.suggestion) + '</span>?';
                html += '</div>';
            }
            
            html += '<div class="no-results">';
            html += '<div class="no-results-icon">🔍</div>';
            html += '<div>No results found. Try different keywords.</div>';
            html += '</div>';
            
            if (container) {
                container.insertAdjacentHTML('beforebegin', html);
            } else {
                mainContainer.insertAdjacentHTML('beforeend', html);
            }
            
            // Setup suggestion click
            const suggestionLink = document.querySelector('.spell-suggestion-link');
            if (suggestionLink) {
                suggestionLink.addEventListener('click', () => {
                    const suggestion = suggestionLink.dataset.suggestion;
                    input.value = suggestion;
                    doSearch(suggestion, 1);
                });
            }
            
            return;
        }
        
        // Has results
        const startNum = (data.page - 1) * data.per_page + 1;
        const endNum = Math.min(data.page * data.per_page, data.total);
        
        // Update or create results info
        let resultsInfoEl = resultsInfo;
        if (!resultsInfoEl) {
            resultsInfoEl = document.createElement('div');
            resultsInfoEl.className = 'results-info';
            mainContainer.insertBefore(resultsInfoEl, mainContainer.firstChild);
        }
        resultsInfoEl.innerHTML = `
            <span class="results-count">✓ Found ${data.total} result${data.total !== 1 ? 's' : ''}</span>
            <span class="results-time">in ${data.elapsed_ms.toFixed(1)}ms</span>
            <span class="results-query">showing ${startNum}-${endNum} for "${escapeHtml(data.query)}"</span>
        `;
        
        // Render facets
        const facetsHtml = renderFacets(data.facets, data.active_facet, data.active_type, data.total_unfiltered);
        if (facetsHtml) {
            resultsInfoEl.insertAdjacentHTML('afterend', facetsHtml);
            setupFacetButtons();
        }
        
        // Render results
        if (!container) {
            container = document.createElement('div');
            container.className = 'results';
            mainContainer.appendChild(container);
        }
        
        container.innerHTML = data.results.map(renderResult).join('');
        
        allLoadedResults = data.results;
        currentPage = data.page;
        totalPages = data.total_pages;
        
        // Setup infinite scroll for more results
        if (currentPage < totalPages) {
            createScrollSentinel();
        }
        
        setupCopyLinkButtons();
    }
    
    function showButtonLoading() {
        searchButton.textContent = '...';
        searchButton.disabled = true;
    }
    
    function hideButtonLoading() {
        searchButton.textContent = 'Search';
        searchButton.disabled = false;
    }
    
    function doSearch(query, page = 1) {
        if (!query || !query.trim()) {
            window.location.href = '/';
            return;
        }
        
        // Cancel pending request
        if (currentRequest) {
            currentRequest.abort();
        }
        
        showButtonLoading();
        hideHistoryDropdown();
        
        // Save to history on first page
        if (page === 1) {
            addToHistory(query);
        }
        
        currentQuery = query;
        
        const params = buildSearchParams(query, page);
        const apiUrl = '/api/search?' + params.toString();
        
        // Update browser URL
        const browserParams = new URLSearchParams(params);
        // Add theme to browser URL
        const theme = getStoredTheme() || (document.body.classList.contains('light') ? 'light' : 'dark');
        if (theme === 'light') browserParams.set('theme', 'light');
        const browserUrl = '/?' + browserParams.toString();
        window.history.pushState({ query, page, facet: currentFacet, type: currentType }, '', browserUrl);
        
        // Create abort controller
        const controller = new AbortController();
        currentRequest = controller;
        
        fetch(apiUrl, { signal: controller.signal })
            .then(response => {
                if (!response.ok) throw new Error('Search failed');
                return response.json();
            })
            .then(data => {
                hideButtonLoading();
                renderResults(data);
            })
            .catch(err => {
                hideButtonLoading();
                if (err.name !== 'AbortError') {
                    console.error('Search error:', err);
                }
            })
            .finally(() => {
                currentRequest = null;
            });
    }
    
    // Debounced search (#173)
    function debouncedSearch() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentFacet = null;
            doSearch(input.value, 1);
        }, DEBOUNCE_MS);
    }
    
    // ========================================================================
    // Event Bindings
    // ========================================================================
    function bindEvents() {
        // Form submit
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            clearTimeout(searchTimeout);
            currentFacet = null;
            doSearch(input.value, 1);
        });
        
        // Input events for instant search
        input.addEventListener('input', debouncedSearch);
        
        // History dropdown
        input.addEventListener('focus', () => {
            if (input.value.length < 3) {
                showHistoryDropdown();
            }
        });
        
        input.addEventListener('blur', () => {
            setTimeout(hideHistoryDropdown, 200);
        });
        
        // Clear button
        const clearBtn = document.querySelector('.search-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                input.value = '';
                input.focus();
                hideHistoryDropdown();
            });
        }
        
        // Keyboard navigation
        document.addEventListener('keydown', handleKeyboardNavigation);
        
        // Browser back/forward
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.query) {
                input.value = e.state.query;
                currentFacet = e.state.facet || null;
                doSearch(e.state.query, e.state.page || 1, currentFacet);
            } else {
                window.location.reload();
            }
        });
        
        // Option changes trigger search
        document.querySelectorAll('select[name="sort"], select[name="limit"]').forEach(select => {
            select.addEventListener('change', () => {
                if (currentQuery) {
                    doSearch(currentQuery, 1, currentFacet);
                }
            });
        });
        
        const exactCheckbox = document.querySelector('input[name="exact"]');
        if (exactCheckbox) {
            exactCheckbox.addEventListener('change', () => {
                if (currentQuery) {
                    doSearch(currentQuery, 1, currentFacet);
                }
            });
        }
    }
    
    // ========================================================================
    // Initialization
    // ========================================================================
    function init() {
        initTheme();
        setupThemeToggle();
        setupInfiniteScroll();
        setupFacetButtons();
        setupCopyLinkButtons();
        bindEvents();
        
        // Get initial state from URL
        const urlParams = new URLSearchParams(window.location.search);
        currentQuery = urlParams.get('q') || '';
        currentFacet = urlParams.get('category') || null;
        currentType = urlParams.get('type') || null;
        
        // Expose some functions globally for onclick handlers
        window.docSearch = {
            clearFacet: () => {
                currentFacet = null;
                currentType = null;
                currentPage = 1;
                allLoadedResults = [];
                doSearch(currentQuery, 1);
            },
            clearFacets: () => {
                currentFacet = null;
                currentType = null;
                currentPage = 1;
                allLoadedResults = [];
                doSearch(currentQuery, 1);
            }
        };
    }
    
    init();
})();
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
                    <span class="result-score-pct {score_color}">{score_pct}%</span>
                </span>''' if show_scores else ''
                
                doc_type_badge = f'<span class="doc-type-badge {doc_type}">{doc_type}</span>'
                snippet_html = f'<div class="result-snippet">{snippet}</div>' if snippet else ""
                
                results_html += f'''
                <div class="result">
                    <div class="result-header">
                        <span class="result-number">{i}</span>
                        <a href="{url}" class="result-title" target="_blank" rel="noopener">{title}</a>
                        {doc_type_badge}
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
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)
    
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
                    'facets': r.get('facets', {}),
                    'doc_type': r.get('doc_type', 'html')
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
