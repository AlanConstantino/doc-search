"""
Snippet extraction and term highlighting for search results.

Terminal coloring lives in ``doc_search.app.terminal`` / ``app.cli.formatters``.
"""

import re
from functools import lru_cache
from typing import List, Dict, Any, Optional, Set, FrozenSet, Pattern

from ..core.constants import (
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
    sorted_terms = sorted((t for t in terms if t), key=len, reverse=True)
    if not sorted_terms:
        # Never-matching pattern
        return re.compile(r'(?!x)x')
    pattern = r'\b(' + '|'.join(re.escape(t) for t in sorted_terms) + r')\b'
    return re.compile(pattern, re.IGNORECASE)


def highlight_terms(text: str, terms: Set[str], marker: str = '**') -> str:
    """
    Highlight search terms in text using markers.

    Only whole-word matches of the provided terms are wrapped. Callers should
    pass the *original* query terms (not large expansion sets) so result
    blurbs stay readable.
    """
    if not terms or not text:
        return text

    cleaned = set()
    for t in terms:
        if not t:
            continue
        tl = str(t).lower().strip()
        if not tl or tl.endswith('*'):
            continue
        if len(tl) < 2 and not tl.isdigit():
            continue
        cleaned.add(tl)
    if not cleaned:
        return text

    terms_frozen = frozenset(cleaned)
    pattern = _compile_terms_pattern(terms_frozen)

    def replacer(match):
        word = match.group(0)
        return f"{marker}{word}{marker}"

    return pattern.sub(replacer, text)



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
_SNIPPET_WORD_PATTERN = re.compile(r'\b(?:0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)+|\d+[A-Za-z][A-Za-z0-9_]*|[A-Za-z][A-Za-z0-9_]*|\d+)\b')


def normalize_document_text(text: str) -> str:
    """Normalize extracted document text for better snippet display.
    
    Cleans up common artifacts from PDF and Word extraction:
    - Joins broken lines (mid-sentence line breaks from PDF column layout)
    - Collapses excessive whitespace
    - Removes orphaned bullets/numbers from broken formatting
    - Normalizes unicode whitespace
    """
    if not text:
        return text
    
    # Normalize unicode whitespace (non-breaking spaces, etc.)
    text = re.sub(r'[\xa0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000]', ' ', text)
    
    # Remove soft hyphens
    text = text.replace('\xad', '')
    
    # Collapse runs of whitespace first (preserve newline structure)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Join broken lines — aggressively merge single newlines into spaces.
    # Only preserve double newlines (paragraph breaks).
    # PDF text is full of hard line breaks from column layouts, page widths, etc.
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    
    # Collapse any resulting double spaces
    text = re.sub(r'  +', ' ', text)
    
    return text.strip()


def find_best_snippet(text: str, terms: Set[str], phrases: List[List[str]],
                       snippet_length: int = DEFAULT_SNIPPET_LENGTH) -> str:
    """
    Find the most relevant snippet from text.

    Strategy:
        1. Locate query-term matches
        2. Score nearby windows by term density / phrase hits
        3. Return ~snippet_length chars centered on the best cluster
    """
    if not text:
        return ""

    text = text.strip()
    snippet_length = max(40, int(snippet_length or DEFAULT_SNIPPET_LENGTH))

    matches = list(_SNIPPET_WORD_PATTERN.finditer(text))
    if not matches:
        if len(text) <= snippet_length:
            return text
        return text[:snippet_length].rsplit(' ', 1)[0] + '...'

    all_query_terms = {t.lower() for t in (terms or set()) if t}
    for phrase in phrases or []:
        all_query_terms.update(w.lower() for w in phrase if w)

    word_lower = [m.group(0).lower() for m in matches]
    term_positions = [i for i, w in enumerate(word_lower) if w in all_query_terms]

    # No query terms in body → plain lead-in, do not pretend relevance
    if not term_positions:
        if len(text) <= snippet_length:
            return text
        cut = text[:snippet_length].rsplit(' ', 1)[0]
        return cut + '...'

    # Very short docs: whole text is fine
    if len(text) <= min(snippet_length, 120):
        return text

    window_words = SNIPPET_WINDOW_WORDS
    best_score = -1
    best_start = 0

    candidate_starts = set()
    for pos in term_positions:
        for offset in range(-window_words, 1):
            candidate = pos + offset
            if 0 <= candidate < len(matches):
                candidate_starts.add(candidate)

    for i in sorted(candidate_starts):
        window_end = min(i + window_words, len(matches))
        score = 0
        found_terms = set()
        for j in range(i, window_end):
            if word_lower[j] in all_query_terms:
                score += 1
                found_terms.add(word_lower[j])
        score += len(found_terms) * TERM_DIVERSITY_BONUS

        if phrases:
            window_start_char = matches[i].start()
            window_end_char = matches[window_end - 1].end() if window_end > i else window_start_char + snippet_length
            window_text = text[window_start_char:window_end_char + 50]
            for phrase in phrases:
                if check_phrase_match(window_text, phrase):
                    score += PHRASE_MATCH_BONUS

        if score > best_score:
            best_score = score
            best_start = i

    # Character window centered on the best match cluster
    end_word_idx = min(best_start + window_words, len(matches) - 1)
    region_start = matches[best_start].start()
    region_end = matches[end_word_idx].end()
    region_mid = (region_start + region_end) // 2
    half = max(40, snippet_length // 2)
    start_char = max(0, region_mid - half)
    end_char = min(len(text), start_char + snippet_length)
    if end_char - start_char < snippet_length and start_char > 0:
        start_char = max(0, end_char - snippet_length)

    if start_char > 0:
        space_pos = text.rfind(' ', 0, start_char + 1)
        if space_pos != -1 and space_pos > start_char - 40:
            start_char = space_pos + 1
    if end_char < len(text):
        space_pos = text.find(' ', end_char)
        if space_pos != -1 and space_pos < end_char + 40:
            end_char = space_pos

    snippet = text[start_char:end_char].strip()
    if start_char > 0:
        snippet = '...' + snippet
    if end_char < len(text):
        snippet = snippet + '...'
    return snippet

