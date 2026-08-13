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
    // Suggest-as-you-type (#autocomplete)
    // ========================================================================
    let suggestDropdown = null;
    let suggestActiveIndex = -1;
    let suggestTimeout = null;
    let suggestAbort = null;
    const SUGGEST_DEBOUNCE_MS = 150;
    const SUGGEST_MIN_CHARS = 2;

    function createSuggestDropdown() {
        if (suggestDropdown) return suggestDropdown;
        const dropdown = document.createElement('div');
        dropdown.className = 'suggest-dropdown';
        const wrapper = document.querySelector('.search-input-wrapper');
        if (wrapper) {
            wrapper.appendChild(dropdown);
        }
        suggestDropdown = dropdown;
        return dropdown;
    }

    const DOC_TYPE_ICONS = {
        'html': '🌐', 'pdf': '📄', 'docx': '📝', 'xlsx': '📊',
    };

    function showSuggestDropdown(suggestions, query) {
        if (!suggestions || suggestions.length === 0) {
            hideSuggestDropdown();
            return;
        }
        const dropdown = createSuggestDropdown();
        suggestActiveIndex = -1;

        const queryLower = query.toLowerCase();
        let html = '';
        suggestions.forEach((s, i) => {
            // Support both string and object formats
            const text = typeof s === 'string' ? s : (s.text || '');
            const displayText = typeof s === 'object' ? (s.display_text || s.text || '') : s;
            const docType = typeof s === 'object' ? s.doc_type : null;
            const icon = docType ? (DOC_TYPE_ICONS[docType] || '🔍') : '🔍';

            // Highlight the matching prefix in display text
            const textLower = displayText.toLowerCase();
            let display;
            const idx = textLower.indexOf(queryLower);
            if (idx >= 0) {
                display = escapeHtml(displayText.substring(0, idx))
                    + '<mark>' + escapeHtml(displayText.substring(idx, idx + query.length)) + '</mark>'
                    + escapeHtml(displayText.substring(idx + query.length));
            } else {
                display = escapeHtml(displayText);
            }
            html += '<div class="suggest-item" data-index="' + i + '" data-value="' + escapeHtml(text) + '">'
                + '<span class="suggest-icon">' + icon + '</span>'
                + '<span class="suggest-text">' + display + '</span>'
                + '</div>';
        });
        dropdown.innerHTML = html;
        dropdown.classList.add('visible');
        hideHistoryDropdown();

        // Click handlers
        dropdown.querySelectorAll('.suggest-item').forEach(item => {
            item.addEventListener('mousedown', (e) => {
                e.preventDefault(); // Prevent input blur
                const val = item.dataset.value;
                input.value = val;
                hideSuggestDropdown();
                clearTimeout(searchTimeout);
                doSearch(val, 1);
            });
        });
    }

    function hideSuggestDropdown() {
        if (suggestDropdown) {
            suggestDropdown.classList.remove('visible');
        }
        suggestActiveIndex = -1;
    }

    function suggestNavigate(direction) {
        if (!suggestDropdown || !suggestDropdown.classList.contains('visible')) return false;
        const items = suggestDropdown.querySelectorAll('.suggest-item');
        if (items.length === 0) return false;

        // Remove current active
        if (suggestActiveIndex >= 0 && suggestActiveIndex < items.length) {
            items[suggestActiveIndex].classList.remove('active');
        }

        suggestActiveIndex += direction;
        if (suggestActiveIndex < -1) suggestActiveIndex = items.length - 1;
        if (suggestActiveIndex >= items.length) suggestActiveIndex = -1;

        if (suggestActiveIndex >= 0) {
            items[suggestActiveIndex].classList.add('active');
            items[suggestActiveIndex].scrollIntoView({ block: 'nearest' });
            input.value = items[suggestActiveIndex].dataset.value;
        }
        return true;
    }

    function suggestSelect() {
        if (!suggestDropdown || !suggestDropdown.classList.contains('visible')) return false;
        if (suggestActiveIndex < 0) return false;
        const items = suggestDropdown.querySelectorAll('.suggest-item');
        if (suggestActiveIndex < items.length) {
            const val = items[suggestActiveIndex].dataset.value;
            input.value = val;
            hideSuggestDropdown();
            clearTimeout(searchTimeout);
            doSearch(val, 1);
            return true;
        }
        return false;
    }

    function fetchSuggestions(query) {
        clearTimeout(suggestTimeout);
        if (suggestAbort) {
            suggestAbort.abort();
            suggestAbort = null;
        }
        if (!query || query.length < SUGGEST_MIN_CHARS) {
            hideSuggestDropdown();
            return;
        }
        suggestTimeout = setTimeout(() => {
            const controller = new AbortController();
            suggestAbort = controller;
            fetch('/suggest?q=' + encodeURIComponent(query) + '&limit=8', { signal: controller.signal })
                .then(r => r.json())
                .then(data => {
                    suggestAbort = null;
                    if (data.suggestions && data.suggestions.length > 0 && input.value.trim() === query) {
                        showSuggestDropdown(data.suggestions, query);
                    } else {
                        hideSuggestDropdown();
                    }
                })
                .catch(e => {
                    if (e.name !== 'AbortError') {
                        hideSuggestDropdown();
                    }
                });
        }, SUGGEST_DEBOUNCE_MS);
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
            result.focus({ preventScroll: true });
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
        // Don't navigate results while suggest dropdown is open
        if (suggestDropdown && suggestDropdown.classList.contains('visible')) {
            return;
        }
        
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
        document.querySelectorAll('.copy-link-btn').forEach(btn => {
            if (btn.dataset.bound) return;
            btn.dataset.bound = '1';
            btn.addEventListener('click', () => {
                const url = btn.dataset.url || btn.closest('.result')?.querySelector('.result-title')?.href;
                if (url) copyLink(btn, url);
            });
        });
    }
    
    function copyLink(btn, url) {
        navigator.clipboard.writeText(url).then(() => {
            btn.innerHTML = '📋 Copied!';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = '📋 Copy link';
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
            btn.innerHTML = '📋 Copied!';
            btn.classList.add('copied');
            setTimeout(() => {
                btn.innerHTML = '📋 Copy link';
                btn.classList.remove('copied');
            }, 2000);
        });
    }
    
    function setupClickTracking() {
        document.querySelectorAll('.result-title').forEach(link => {
            if (link.dataset.tracked) return;
            link.dataset.tracked = '1';
            link.addEventListener('click', () => {
                const result = link.closest('.result');
                const rank = result ? result.querySelector('.result-number')?.textContent : '0';
                const q = document.querySelector('.search-input')?.value || '';
                fetch('/api/click', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: q, url: link.href, rank: parseInt(rank) || 0})
                }).catch(() => {});
            });
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
        return escapeHtml(text).replace(/\*\*([^*]+)\*\*/g, '<mark>$1</mark>');
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
        const docIcons = {pdf:'📄',docx:'📝',xlsx:'📊',pptx:'📊',html:'🌐'};
        const docIcon = docIcons[docType] || docIcons.html;
        const docTypeBadge = `<span class="doc-type-badge ${docType}">${docIcon} ${docType}</span>`;
        
        // Action buttons: web pages get Visit + Copy, files get Download + Copy
        const isFile = r.url.startsWith('/files/');
        let actionsHtml = '<div class="result-actions">';
        if (isFile) {
            const downloadUrl = r.url.split('#')[0] + '?download=1';
            actionsHtml += `<a href="${escapeHtml(downloadUrl)}" class="result-action-btn" title="Download file">⬇ Download</a>`;
        } else {
            actionsHtml += `<a href="${escapeHtml(r.url)}" class="result-action-btn" target="_blank" rel="noopener" title="Visit site">🔗 Visit</a>`;
        }
        actionsHtml += `<button class="result-action-btn copy-link-btn" data-url="${escapeHtml(r.original_url || r.url)}" title="Copy link">📋 Copy link</button>`;
        actionsHtml += '</div>';
        
        return `
            <div class="result" tabindex="-1" data-url="${escapeHtml(r.url)}">
                <div class="result-header">
                    <span class="result-number">${r.rank}</span>
                    <a href="${escapeHtml(r.url)}" class="result-title" target="_blank" rel="noopener">${escapeHtml(r.title)}</a>
                    ${docTypeBadge}
                    <span class="result-score" title="Score: ${r.score.toFixed(2)}">
                        <span class="result-score-bar"><span class="result-score-fill ${scoreClass}" style="width: ${r.score_pct}%"></span></span>
                        <span class="result-score-pct ${scoreClass}">${r.score_pct}% <span style="opacity:0.5;font-size:0.85em">(${r.score.toFixed(2)})</span></span>
                    </span>
                </div>
                <div class="result-url">${escapeHtml(r.original_url || r.url)}</div>
                ${snippet}
                ${actionsHtml}
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
        setupClickTracking();
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
            <a href="/api/search?q=${encodeURIComponent(data.query)}&format=csv&limit=50" class="result-action-btn" style="margin-left:8px;font-size:0.85em" title="Export as CSV">Export CSV</a>
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
        setupClickTracking();
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
            hideSuggestDropdown();
            currentFacet = null;
            doSearch(input.value, 1);
        });
        
        // Input events for instant search + suggest-as-you-type
        input.addEventListener('input', () => {
            const val = input.value.trim();
            fetchSuggestions(val);
            debouncedSearch();
        });
        
        // Keyboard handling for suggest dropdown
        input.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                if (suggestDropdown && suggestDropdown.classList.contains('visible')) {
                    e.preventDefault();
                    suggestNavigate(1);
                }
            } else if (e.key === 'ArrowUp') {
                if (suggestDropdown && suggestDropdown.classList.contains('visible')) {
                    e.preventDefault();
                    suggestNavigate(-1);
                }
            } else if (e.key === 'Enter') {
                if (suggestSelect()) {
                    e.preventDefault();
                }
            } else if (e.key === 'Escape') {
                hideSuggestDropdown();
            }
        });
        
        // History dropdown
        input.addEventListener('focus', () => {
            if (input.value.length < SUGGEST_MIN_CHARS) {
                showHistoryDropdown();
            }
        });
        
        input.addEventListener('blur', () => {
            setTimeout(() => {
                hideHistoryDropdown();
                hideSuggestDropdown();
            }, 200);
        });
        
        // Clear button
        const clearBtn = document.querySelector('.search-clear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                input.value = '';
                input.focus();
                hideHistoryDropdown();
                hideSuggestDropdown();
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
        setupClickTracking();
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
