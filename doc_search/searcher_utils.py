"""
Utility functions for search result formatting and highlighting.

This module contains:
- highlight_terms: Mark up search terms with text markers
- highlight_terms_ansi: Mark up search terms with ANSI colors
- find_best_snippet: Extract the most relevant snippet from text
- format_results: Format search results for display
"""

import re
from functools import lru_cache
from typing import List, Dict, Any, Optional, Set, FrozenSet, Pattern

from .utils import highlight_match, style_title, style_url, style_score, style_number, style_info, style_success
from .constants import (
    DEFAULT_SNIPPET_LENGTH, MAX_SNIPPET_LENGTH, MAX_TITLE_LENGTH,
    SNIPPET_WINDOW_WORDS, PHRASE_MATCH_BONUS, TERM_DIVERSITY_BONUS
)


@lru_cache(maxsize=256)
def _compile_terms_pattern(terms: FrozenSet[str]) -> Pattern:
    """
    Compile a regex pattern for a set of terms.
    
    Uses LRU cache to avoid recompiling the same pattern repeatedly.
    
    Args:
        terms: Frozen set of terms to match
        
    Returns:
        Compiled regex pattern
    """
    # Sort by length (longest first) to match longer terms before shorter ones
    sorted_terms = sorted(terms, key=len, reverse=True)
    pattern = r'\b(' + '|'.join(re.escape(t) for t in sorted_terms) + r')\b'
    return re.compile(pattern, re.IGNORECASE)


def highlight_terms(text: str, terms: Set[str], marker: str = '**') -> str:
    """
    Highlight search terms in text using markers.
    
    Args:
        text: Text to highlight
        terms: Set of terms to highlight (lowercase)
        marker: Marker to wrap terms with (e.g., '**' or 'CAPS')
        
    Returns:
        Text with highlighted terms
    """
    if not terms or not text:
        return text
    
    # Convert to frozenset for caching
    terms_frozen = frozenset(terms)
    pattern = _compile_terms_pattern(terms_frozen)
    
    def replacer(match):
        word = match.group(0)
        if word.lower() in terms:
            return f"{marker}{word}{marker}"
        return word
    
    return pattern.sub(replacer, text)


def highlight_terms_ansi(text: str, terms: Set[str]) -> str:
    """
    Highlight search terms in text using ANSI color codes.
    
    Args:
        text: Text to highlight
        terms: Set of terms to highlight (lowercase)
        
    Returns:
        Text with ANSI-highlighted terms
    """
    if not terms or not text:
        return text
    
    # Use cached pattern compilation
    terms_frozen = frozenset(terms)
    pattern = _compile_terms_pattern(terms_frozen)
    
    def replacer(match):
        word = match.group(0)
        if word.lower() in terms:
            return highlight_match(word)
        return word
    
    return pattern.sub(replacer, text)


@lru_cache(maxsize=128)
def _compile_phrase_pattern(phrase_words: tuple) -> Pattern:
    """
    Compile a regex pattern for phrase matching.
    
    Args:
        phrase_words: Tuple of words to match in order
        
    Returns:
        Compiled regex pattern
    """
    pattern_parts = [re.escape(word) for word in phrase_words]
    pattern = r'\b' + r'\s+'.join(pattern_parts) + r'\b'
    return re.compile(pattern, re.IGNORECASE)


def check_phrase_match(text: str, phrase_words: List[str]) -> bool:
    """
    Check if a phrase appears in text (words must be adjacent, separated by whitespace).
    
    Args:
        text: Text to search in
        phrase_words: List of words that must appear in order
        
    Returns:
        True if phrase is found
        
    Note:
        Words must be separated by whitespace, not hyphens or other characters.
        "quick brown" matches "quick brown" but NOT "quick-brown".
    """
    if not phrase_words:
        return True
    
    if not text:
        return False
    
    # Use cached pattern compilation
    pattern = _compile_phrase_pattern(tuple(phrase_words))
    return bool(pattern.search(text.lower()))


# Pre-compiled pattern for snippet word matching
_SNIPPET_WORD_PATTERN = re.compile(r'\b[a-zA-Z][a-zA-Z0-9_]*\b')


def find_best_snippet(text: str, terms: Set[str], phrases: List[List[str]], 
                       snippet_length: int = DEFAULT_SNIPPET_LENGTH) -> str:
    """
    Find the most relevant snippet from text.
    
    Strategy:
        1. Find section with highest query term density
        2. Prefer sections containing phrase matches
        3. Return ~snippet_length chars of context
    
    Args:
        text: Full document text
        terms: Set of search terms (lowercase)
        phrases: List of phrase word lists
        snippet_length: Target snippet length in chars
        
    Returns:
        Most relevant snippet from text
    """
    if not text:
        return ""
    
    text = text.strip()
    
    # If text is short enough, return it all
    if len(text) <= snippet_length:
        return text
    
    # Tokenize text with positions using pre-compiled pattern
    matches = list(_SNIPPET_WORD_PATTERN.finditer(text))
    
    if not matches:
        return text[:snippet_length] + '...'
    
    # Score each position by term density in surrounding window
    window_words = SNIPPET_WINDOW_WORDS
    best_score = -1
    best_start = 0
    
    all_query_terms = set(terms)
    for phrase in phrases:
        all_query_terms.update(phrase)
    
    for i in range(len(matches)):
        # Calculate score for window starting at this word
        window_end = min(i + window_words, len(matches))
        window_matches = matches[i:window_end]
        
        score = 0
        found_terms = set()
        
        for m in window_matches:
            word_lower = m.group(0).lower()
            if word_lower in all_query_terms:
                score += 1
                found_terms.add(word_lower)
        
        # Bonus for having multiple different terms
        score += len(found_terms) * TERM_DIVERSITY_BONUS
        
        # Check for phrase matches in this window
        if phrases:
            window_start_char = matches[i].start()
            window_end_char = window_matches[-1].end() if window_matches else window_start_char + snippet_length
            window_text = text[window_start_char:window_end_char + 50]
            
            for phrase in phrases:
                if check_phrase_match(window_text, phrase):
                    score += PHRASE_MATCH_BONUS
        
        if score > best_score:
            best_score = score
            best_start = i
    
    # Extract snippet around best position
    start_match = matches[best_start]
    start_char = max(0, start_match.start() - 20)
    
    # Find end position
    end_word_idx = min(best_start + window_words, len(matches) - 1)
    end_char = min(len(text), matches[end_word_idx].end() + 20)
    
    # Adjust to word boundaries
    if start_char > 0:
        # Find previous space
        space_pos = text.rfind(' ', 0, start_char)
        if space_pos > start_char - 30:
            start_char = space_pos + 1
    
    if end_char < len(text):
        # Find next space
        space_pos = text.find(' ', end_char)
        if space_pos != -1 and space_pos < end_char + 30:
            end_char = space_pos
    
    snippet = text[start_char:end_char]
    
    # Add ellipsis if truncated
    if start_char > 0:
        snippet = '...' + snippet
    if end_char < len(text):
        snippet = snippet + '...'
    
    return snippet


def format_results(
    results: List[Dict[str, Any]], 
    show_scores: bool = False,
    query_terms: Optional[Set[str]] = None,
    elapsed_ms: Optional[float] = None,
    colorize_output: bool = True
) -> str:
    """
    Format search results for display with beautiful ANSI colors.
    
    Args:
        results: List of result dictionaries
        show_scores: Include BM25 scores in output
        query_terms: Set of query terms for ANSI highlighting (optional)
        elapsed_ms: Search time in milliseconds (optional)
        colorize_output: Use ANSI colors (default: True)
        
    Returns:
        Formatted string
    """
    if not results:
        if colorize_output:
            return style_info("No results found.")
        return "No results found."
    
    lines = []
    
    # Performance header
    if elapsed_ms is not None:
        perf_line = f"Found {len(results)} results in {elapsed_ms:.1f}ms"
        if colorize_output:
            lines.append(style_success(f"✓ {perf_line}"))
        else:
            lines.append(perf_line)
        lines.append("")
    
    for i, result in enumerate(results, 1):
        title = result.get('title', 'Untitled') or 'Untitled'
        url = result['url']
        # Prefer snippet (with highlighting) over description
        snippet = result.get('snippet', '') or result.get('description', '')
        score = result.get('score', 0)
        
        # Truncate title if too long
        if len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH - 3] + '...'
        
        # Truncate snippet
        if len(snippet) > MAX_SNIPPET_LENGTH:
            snippet = snippet[:MAX_SNIPPET_LENGTH - 3] + '...'
        
        # Apply ANSI highlighting to snippet if we have query terms
        if colorize_output and query_terms and snippet:
            # Convert **term** markers to ANSI codes
            snippet = re.sub(
                r'\*\*([^*]+)\*\*',
                lambda m: highlight_match(m.group(1)),
                snippet
            )
        
        # Build the result lines with colors
        if colorize_output:
            if show_scores:
                lines.append(f"{style_number(i)} {style_score(score)} {style_title(title)}")
            else:
                lines.append(f"{style_number(i)} {style_title(title)}")
            
            lines.append(f"   {style_url(url)}")
            
            if snippet:
                lines.append(f"   {snippet}")
        else:
            # Plain text output
            if show_scores:
                lines.append(f"{i}. [{score:.4f}] {title}")
            else:
                lines.append(f"{i}. {title}")
            
            lines.append(f"   {url}")
            
            if snippet:
                lines.append(f"   {snippet}")
        
        lines.append("")
    
    return "\n".join(lines)
