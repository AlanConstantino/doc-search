"""
Smart suggestion engine for search autocomplete.

Scores suggestion entries (page titles, section headings, filenames)
against user input using multi-term matching, prefix boosting,
and optional fuzzy expansion via SymSpell.

Architecture:
    User types "pythn clas"
        ↓
    [1] Tokenize → ["pythn", "clas"]
        ↓
    [2] Fuzzy expand → {"pythn": ["python"], "clas": ["class", "classes"]}
        ↓
    [3] Score all entries against original + expanded terms
        ↓
    [4] Return top N, sorted by score
"""

import json
import gzip
import re
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple


# Headings to skip (navigation, boilerplate)
_SKIP_HEADINGS = {
    'navigation', 'table of contents', 'contents', 'menu',
    'previous topic', 'next topic', 'this page', 'see also',
    'references', 'external links', 'footnotes', 'notes',
    'sidebar', 'breadcrumb', 'footer', 'header',
}

# Min heading length to be useful as a suggestion
_MIN_HEADING_LEN = 4

# Max heading level to index (h1-h3 are useful, h4+ are too granular)
_MAX_HEADING_LEVEL = 3

# Scoring constants
_WEIGHT_TITLE = 100       # Base weight for page titles
_WEIGHT_H1 = 80           # Base weight for h1 headings
_WEIGHT_H2 = 60           # h2
_WEIGHT_H3 = 40           # h3

_BONUS_PREFIX_START = 30   # Entry text starts with the user's term
_BONUS_WORD_PREFIX = 20    # A word in the entry starts with the user's term
_BONUS_SUBSTRING = 5       # Term found as substring anywhere
_BONUS_ALL_TERMS = 25      # All query terms matched
_BONUS_EXACT_TERM = 10     # Exact word match (not just prefix)
_BONUS_EARLY_POSITION = 8  # Term matches in first word of entry

_PENALTY_FUZZY = 5         # Per-term penalty when match came from fuzzy expansion


class TitleSuggester:
    """
    Indexes page titles and headings for autocomplete suggestions.
    
    Each entry has:
    - text: the suggestion text (title or heading)
    - display_text: optional display override (e.g. with heading markers)
    - doc_type: web/pdf/docx/xlsx
    - url: the page URL
    - weight: base relevance weight (titles > h1 > h2 > h3)
    - words: pre-tokenized lowercase words for fast matching
    """
    
    def __init__(self):
        self.entries: List[Dict] = []
        self._seen: set = set()
    
    def add_page(self, title: str, url: str, doc_type: str = 'html',
                 headings: Optional[List] = None):
        """
        Add a page's title and headings to the suggestion index.
        
        Args:
            title: Page title
            url: Page URL
            doc_type: Document type (html, pdf, docx, xlsx)
            headings: List of [level, text] pairs
        """
        if title and len(title.strip()) >= _MIN_HEADING_LEN:
            clean_title = self._clean_text(title)
            if clean_title and clean_title.lower() not in self._seen:
                self._seen.add(clean_title.lower())
                self.entries.append({
                    'text': clean_title,
                    'doc_type': doc_type,
                    'url': url,
                    'weight': _WEIGHT_TITLE,
                    'words': self._tokenize(clean_title),
                })
        
        if headings:
            for heading in headings:
                if not isinstance(heading, (list, tuple)) or len(heading) < 2:
                    continue
                level, text = heading[0], heading[1]
                if not isinstance(level, int) or level > _MAX_HEADING_LEVEL:
                    continue
                if not text or len(text.strip()) < _MIN_HEADING_LEN:
                    continue
                
                clean = self._clean_text(text)
                if not clean or clean.lower() in self._seen:
                    continue
                if clean.lower() in _SKIP_HEADINGS:
                    continue
                
                self._seen.add(clean.lower())
                weight = max(10, 100 - level * 20)  # h1=80, h2=60, h3=40
                self.entries.append({
                    'text': clean,
                    'display_text': '#' * level + ' ' + clean,
                    'doc_type': doc_type,
                    'url': url,
                    'weight': weight,
                    'words': self._tokenize(clean),
                })
    
    def _clean_text(self, text: str) -> str:
        """Clean suggestion text."""
        text = text.strip()
        text = text.rstrip('¶').strip()
        text = re.sub(r'^\d+(\.\d+)*\.?\s*', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lowercase words for matching."""
        return [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', text) if len(w) >= 1]
    
    def _score_entry(
        self,
        entry: Dict,
        query_terms: List[str],
        expanded_terms: Optional[Dict[str, List[str]]] = None,
    ) -> float:
        """
        Score an entry against query terms.
        
        Args:
            entry: Suggestion entry dict
            query_terms: Original user query tokens (lowercase)
            expanded_terms: Optional dict of original_term -> [fuzzy_expansions]
            
        Returns:
            Relevance score (higher = better), or 0 if no match
        """
        entry_text_lower = entry['text'].lower()
        entry_words = entry.get('words') or self._tokenize(entry['text'])
        base_weight = entry.get('weight', 50)
        
        score = 0.0
        terms_matched = 0
        
        for q_term in query_terms:
            term_score = self._score_term_against_entry(
                q_term, entry_text_lower, entry_words, is_fuzzy=False
            )
            
            # If original term didn't match, try fuzzy expansions
            if term_score == 0 and expanded_terms and q_term in expanded_terms:
                best_fuzzy = 0.0
                for expansion in expanded_terms[q_term]:
                    fuzzy_score = self._score_term_against_entry(
                        expansion, entry_text_lower, entry_words, is_fuzzy=True
                    )
                    best_fuzzy = max(best_fuzzy, fuzzy_score)
                term_score = best_fuzzy
            
            if term_score > 0:
                terms_matched += 1
            score += term_score
        
        if terms_matched == 0:
            return 0.0
        
        # Bonus for matching ALL query terms
        if terms_matched == len(query_terms) and len(query_terms) > 1:
            score += _BONUS_ALL_TERMS
        
        # Scale by fraction of terms matched (partial matches are less useful)
        match_ratio = terms_matched / len(query_terms)
        score *= match_ratio
        
        # Apply base weight (title > h1 > h2 > h3)
        score += base_weight * match_ratio
        
        return score
    
    def _score_term_against_entry(
        self,
        term: str,
        entry_text_lower: str,
        entry_words: List[str],
        is_fuzzy: bool = False,
    ) -> float:
        """Score a single term against an entry."""
        score = 0.0
        
        # Check if entry text starts with term (strongest signal)
        if entry_text_lower.startswith(term):
            score += _BONUS_PREFIX_START
        
        # Check word-level matches
        word_matched = False
        for i, word in enumerate(entry_words):
            if word == term:
                score += _BONUS_EXACT_TERM
                if i == 0:
                    score += _BONUS_EARLY_POSITION
                word_matched = True
                break
            elif word.startswith(term):
                score += _BONUS_WORD_PREFIX
                if i == 0:
                    score += _BONUS_EARLY_POSITION
                word_matched = True
                break
        
        if not word_matched and term in entry_text_lower:
            # Substring match (weakest)
            score += _BONUS_SUBSTRING
        
        # Penalize fuzzy matches
        if is_fuzzy and score > 0:
            score -= _PENALTY_FUZZY
            score = max(1.0, score)  # Keep it positive
        
        return score
    
    def suggest(
        self,
        query: str,
        max_suggestions: int = 8,
        symspell=None,
    ) -> List[Dict]:
        """
        Get suggestions matching a query with multi-term and fuzzy support.
        
        Args:
            query: User input (may be partial, multi-word, have typos)
            max_suggestions: Maximum results
            symspell: Optional SymSpell instance for fuzzy expansion
            
        Returns:
            List of dicts with 'text', 'display_text', 'doc_type', 'url'
        """
        if not query or len(query.strip()) < 2:
            return []
        
        # Step 1: Tokenize query
        query_terms = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', query) if len(w) >= 1]
        if not query_terms:
            return []
        
        # Step 2: Fuzzy expand each term via SymSpell
        expanded_terms: Dict[str, List[str]] = {}
        if symspell:
            for term in query_terms:
                if len(term) >= 2:
                    matches = symspell.lookup(term, max_distance=1, max_results=3)
                    expansions = []
                    for word, dist, freq in matches:
                        if dist > 0:  # Only include actual corrections
                            expansions.append(word)
                    if expansions:
                        expanded_terms[term] = expansions
        
        # Step 3: Score all entries
        scored = []
        for entry in self.entries:
            score = self._score_entry(entry, query_terms, expanded_terms)
            if score > 0:
                scored.append((entry, score))
        
        # Step 4: Sort by score desc, then alphabetically
        scored.sort(key=lambda x: (-x[1], x[0]['text'].lower()))
        
        # Return top N (strip internal fields like 'words')
        results = []
        for entry, _ in scored[:max_suggestions]:
            results.append({
                'text': entry['text'],
                'display_text': entry.get('display_text', entry['text']),
                'doc_type': entry.get('doc_type'),
                'url': entry.get('url'),
            })
        
        return results
    
    def build_from_pages(self, pages_dir: Path, verbose: bool = False) -> int:
        """
        Build suggestion index from a pages directory.
        
        Args:
            pages_dir: Path to directory containing page JSON files
            verbose: Print progress
            
        Returns:
            Number of entries indexed
        """
        if not pages_dir.exists():
            return 0
        
        count = 0
        for page_file in sorted(pages_dir.glob('*.json')):
            try:
                with open(page_file) as f:
                    data = json.load(f)
                
                title = data.get('title', '')
                url = data.get('url', '')
                doc_type = data.get('doc_type', 'html')
                headings = data.get('headings', [])
                
                self.add_page(title, url, doc_type, headings)
                count += 1
            except (json.JSONDecodeError, IOError):
                continue
        
        if verbose:
            print(f"Title suggester: {len(self.entries)} entries from {count} pages")
        
        return len(self.entries)
    
    def save(self, path: str, compress: bool = True) -> Path:
        """Save suggestion index to disk."""
        data = {
            'version': 2,
            'entries': [
                {k: v for k, v in e.items() if k != 'words'}
                for e in self.entries
            ],
        }
        
        if compress:
            out_path = Path(f"{path}.json.gz")
            with gzip.open(out_path, 'wt', encoding='utf-8') as f:
                json.dump(data, f)
        else:
            out_path = Path(f"{path}.json")
            with open(out_path, 'w') as f:
                json.dump(data, f, indent=2)
        
        return out_path
    
    @classmethod
    def load(cls, path: str) -> 'TitleSuggester':
        """Load suggestion index from disk."""
        path = Path(path)
        
        if path.suffix == '.gz':
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
        else:
            with open(path) as f:
                data = json.load(f)
        
        suggester = cls()
        suggester.entries = data.get('entries', [])
        # Rebuild derived fields
        for entry in suggester.entries:
            entry['words'] = suggester._tokenize(entry['text'])
        suggester._seen = {e['text'].lower() for e in suggester.entries}
        
        return suggester
    
    def get_stats(self) -> Dict:
        """Get stats about the suggestion index."""
        type_counts = {}
        for entry in self.entries:
            dt = entry.get('doc_type', 'unknown')
            type_counts[dt] = type_counts.get(dt, 0) + 1
        
        return {
            'total_entries': len(self.entries),
            'by_type': type_counts,
        }
